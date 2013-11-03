#:coding=utf-8:

"""
A kombu transport for App Engine's
Pull Task Queue API.
"""

import logging
import socket
import base64
from Queue import Empty
from collections import deque, defaultdict

import httplib2

import anyjson as json

from kombu.transport import virtual
from kombu.utils import cached_property
from kombu.exceptions import (
    StdConnectionError,
    StdChannelError,
)

from apiclient.errors import HttpError
from apiclient.discovery import build
from oauth2client.file import Storage

logger = logging.getLogger(__name__)

def _debug_fun(func_name, args=None, kwargs=None):
    arg_list = []
    if args:
        arg_list.extend(repr(arg) for arg in args)
    if kwargs:
        arg_list.extend('%s=%r' % (k,v) for k,v in kwargs.items())

    logger.debug('%s(%s)' % (func_name, ", ".join(arg_list)))

class Channel(virtual.Channel):
    """
    An implementation of a messaging channel using
    Google App Engine's Pull Task Queue API.
    """
    _service = None
    _credentials = None
    _queue_map = {}             # Map of queue names to queue URIs
    default_num_tasks = 1       # Number of tasks to buffer
    default_lease_secs = 1800   # 30 minutes.

    _noack_queues = set()

    def __init__(self, *args, **kwargs):
        super(Channel, self).__init__(*args, **kwargs)
        self.buffers = defaultdict(lambda: deque())

    def basic_consume(self, queue, no_ack, *args, **kwargs):
        _debug_fun('basic_ack', (queue, no_ack) + args, kwargs)
        if no_ack:
            self._noack_queues.add(queue)
        return super(Channel, self).basic_consume(queue, no_ack,
                                                  *args, **kwargs)

    def basic_cancel(self, consumer_tag):
        _debug_fun('basic_cancel', (consumer_tag,))
        if consumer_tag in self._consumers:
            queue = self._tag_to_queue[consumer_tag]
            self._noack_queues.discard(queue)
        return super(Channel, self).basic_cancel(consumer_tag)

    def basic_ack(self, delivery_tag):
        """
        Acknowledge the message. 
        
        For task queues this generally means that
        task has been completed.
        """
        _debug_fun('basic_ack', (delivery_tag,))
        delivery_info = self.qos.get(delivery_tag).delivery_info
        try:
            queue = delivery_info['taskqueue_queue']
        except KeyError:
            pass
        else:
            self.service.tasks().delete(
                project=self._get_project('delete'),
                taskqueue=queue,
                task=delivery_info['taskqueue_task_id'],
            ).execute()
        super(Channel, self).basic_ack(delivery_tag)

    def _buffer_tasks(self, queue):
        """
        Buffer a number of tasks for consumers.
        """
        lease = self.service.tasks().lease(
            project=self._get_project('get'),
            taskqueue=queue,
            numTasks=self.num_tasks,
            leaseSecs=self.lease_secs,
        ).execute()

        if 'items' in lease and len(lease['items']) > 0:
            for task in lease['items']:
                self.buffers[queue].append(task)

    def _get(self, queue, **kwargs):
        _debug_fun('_get', (queue,), kwargs)
        
        if not self.buffers[queue]:
            self._buffer_tasks(queue)

        if not self.buffers[queue]:
            raise Empty()

        task = self.buffers[queue].pop()
        payload = json.loads(base64.b64decode(task['payloadBase64']))

        if queue in self._noack_queues:
            # For consumers which don't want to ack we
            # optimistically delete from the queue.
            self.service.tasks().delete(
                project=self._get_project('delete'),
                taskqueue=queue,
                task=task['id'],
            ).execute()
        else:
            # For consumers that do ACK then we need to keep track
            # of the queue name and task id so we can delete it later.
            payload['properties']['delivery_info'].update({
                'taskqueue_task_id': task['id'], 'taskqueue_queue': queue})

        return payload

    def _restore(self, message,
                 unwanted_delivery_info=('taskqueue_task_id', 'taskqueue_queue')):
        """
        Remove unwanted delivery info. The task id and task queue name
        should be JSON serializable but we go ahead and remove them
        here for completeness' sake.
        """
        _debug_fun('_restore', (message, unwanted_delivery_info))
        for unwanted_key in unwanted_delivery_info:
            # Remove objects that aren't JSON serializable.
            message.delivery_info.pop(unwanted_key, None)
        return super(Channel, self)._restore(message)

    def _put(self, queue, message, **kwargs):
        """
        Put a new task in the queue. The task is encoded as JSON
        and converted to base64.
        """
        _debug_fun('_put', (queue, message), kwargs)
        task = self.service.tasks().insert(
            project=self._get_project('insert'),
            taskqueue=queue,
            body={
                # The kind of object returned, in this case set to task.
                "kind": "taskqueues#task", 

                # Name of the queue that the task is in.
                "queueName": queue,

                # A bag of bytes which is the task payload. The payload on 
                # the JSON side is always Base64 encoded.
                "payloadBase64": base64.b64encode(json.dumps(message)),
            }
        ).execute()

        logger.info('Inserted Task: %r', task)

    def _purge(self, queue, **kwargs):
        """
        Attempts to purge the queue by listing and
        deleting all remaining tasks. Because each
        task has to be deleted individually this
        method could take a long time.
        """
        _debug_fun('_purge', (queue,), kwargs)

        while True:
            # list returns a maximum of 100 tasks so
            # continually list the remaining tasks until
            # all tasks are deleted.
            tasks = self.service.tasks().list(
                project=self._get_project('get'),
                taskqueue=queue,
            ).execute()

            if ('items' not in tasks) or (len(tasks['items']) == 0):
                # No more tasks in the queue.
                break
            else:
                for task in tasks['items']:
                    self.service.tasks().delete(
                        project=self._get_project('delete'),
                        taskqueue=queue,
                        task=task['id'],
                    ).execute()

    def _size(self, queue, **kwargs):
        _debug_fun('_size', (queue,), kwargs)

        info = self.service.taskqueues().get(
            project=self._get_project('get'),
            taskqueue=queue,
            getStats=True,
        ).execute()

        logger.info('Got queue info: %r', info)
        
        if 'stats' in info and 'totalTasks' in info['stats']:
            return info['stats']['totalTasks']
        else:
            return 0

    def _has_queue(self, queue, **kwargs):
        _debug_fun('_has_queue', (queue,), kwargs)
        try:
            queue = self.service.taskqueues().get(
                project=self._get_project('get'),
                taskqueue=queue,
            ).execute()
            return queue['id'] == queue
        except HttpError:
            return False

    def _poll(self, *args, **kwargs):
        _debug_fun('_poll', args, kwargs)
        return super(Channel, self)._poll(*args, **kwargs)

    def _get_project(self, op):
        """
        A workaround to an issue where inserts and deletes
        require that the project name have a s~ prefix.

        See: https://code.google.com/p/googleappengine/issues/detail?id=10199
        """
        project_name = self.transport_options.get('project_name')
        hrd_project = self.transport_options.get('hrd_project', False)
        if hrd_project and op in ('insert', 'delete'):
            return 's~%s' % project_name
        else:
            return project_name

    @property
    def credentials(self):
        if self._credentials is None:
            # Load credentials
            # TODO: options
            cred_file = self.transport_options.get('credentials_file')
            storage = Storage(cred_file)
            self._credentials = storage.get()
        return self._credentials

    @property
    def service(self):
        if self._service is None:
            http = httplib2.Http()
            http = self.credentials.authorize(http)
            self._service = build("taskqueue", "v1beta2", http=http)
        return self._service

    @property
    def transport_options(self):
        return self.connection.client.transport_options

    @cached_property
    def num_tasks(self):
        return (self.transport_options.get('num_tasks') or
                self.default_num_tasks)

    @cached_property
    def lease_secs(self):
        return (self.transport_options.get('lease_secs') or
                self.default_lease_secs)

class Transport(virtual.Transport):
    Channel = Channel

    polling_interval = 1.0
    default_port = None
    connection_errors = (StdConnectionError, HttpError, socket.error)
    channel_errors = (HttpError, StdChannelError)
    driver_type = 'appengine_taskqueue'
    driver_name = 'appengine_taskqueue'


def authenticate_main():
    """
    Authenticate using OAuth with the Task Queue API.
    """
    import sys

    import argparse
    from oauth2client import tools
    from oauth2client.client import flow_from_clientsecrets

    if len(sys.argv) > 1 and sys.argv[0] == 'python':
        argv = sys.argv[2:]
    else:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[tools.argparser])

    parser.add_argument('client_secrets', metavar='SECRETS',
                   help='Path to the client_secrets.json.')
    parser.add_argument('credentials', metavar='CREDENTIALS',
                   help='Path where the credentials will be stored.')

    flags = parser.parse_args(argv)

    tools.run_flow(
        flow_from_clientsecrets(flags.client_secrets, scope="https://www.googleapis.com/auth/taskqueue"),
        storage=Storage(flags.credentials),
        flags=flags,
    )
    print('Saved credentials to %s' % flags.credentials)
