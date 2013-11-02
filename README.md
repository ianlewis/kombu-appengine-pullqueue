kombu-appengine-pullqueue
=========================

A kombu backend for the appengine pull queue API. This can be used to create
consumers for tasks from the appengine pull queue API. 

You can find out more about the pull task queue REST API here:
https://developers.google.com/appengine/docs/python/taskqueue/rest/

Setup
=======================

Using the App Engine pull queue REST API requires you to authenticate using
OAuth. You first need set up your project in the Google cloud console.

Follow the directions here about how to set up and register credentials.  When
you register your application be sure to create a "Native" application.

https://developers.google.com/appengine/docs/python/taskqueue/rest/about\_auth

Once you have done that you can authenticate very simply using the provided
authentication utility.

TODO: Not yet done

A Simple Producer 
=======================

A "producer" creates tasks and puts them on the task queue. These tasks are
then processed by a "consumer". Let's look at what a simple producer looks
like.

    conn = Connection(
        transport="kombu_appengine:Transport",
        transport_options={
            'project_name': "my_project",
            'credentials_file': "/path/to/credentials",
        }
    )

    with conn:
        queue = conn.SimpleQueue('pull-queue')
        while True:
            queue.put(json.dumps({'message': message}))
            time.sleep(1)

Here we use the SimpleQueue class from kombu. SimpleQueue has a very similar
api to the native Queue class in python. This producer will create a new tasks
on the task queue with a very simple JSON payload.

A Simple Consumer
=======================

A "consumer" processes tasks from the task queue and removes them once it is
finished processing.

    conn = Connection(
        transport="kombu_appengine:Transport",
        transport_options={
            'project_name': 'my_project',
            'polling_interval': 5,
            'num_tasks': 15,
            'credentials_file': 'credentials',
        }
    )

    try:
        with conn:
            queue = conn.SimpleQueue('pull-queue')
            while True:
                msg = queue.get()
                message = json.loads(msg.body)
                print message['message']
                msg.ack()
    except KeyboardInterrupt:
        print('Exiting.')

We lease the task using the get() method and process it. In this case we are
simply printing the text message we received. After we are finished, we
"acknowledge" we are finished by calling the ack() method on the returned
message object. This deletes the task from the App Engine pull queue.

Suported Transport Options
=============================

The kombu\_appengine transport backend supports several options which can be
set via the transport\_options parameter to the Connection class.

| Option            | Required | Default | Description                                                              |
| ----------------- |:--------:|:-------:|:------------------------------------------------------------------------:|
| project\_name     | required | None    | The Google Cloud Console project                                         |
| hrd\_project      | optional | True    | A boolean option specifying if the app is an HRD app in App Engine.      |
|                   |          |         | This is used as a workaround for API issues. See this issue for details: |
|                   |          |         | https://code.google.com/p/googleappengine/issues/detail?id=10199         |
| credentials\_file | required | None    | The path to the credentials file created after authenticating.           |
| polling\_interval | optional | 1.0     | The number of seconds between polling calls to the pull queue API.       |
| num\_tasks        | optional | 1       | The number of tasks to lease at once and buffer locally for consumption. |

A Note About Celery
=======================

kombu is most often used with celery so I though it wise to add a little note
about celery support. While the kombu API is supported, unfortunately, celery
is not supported because of the inability to create queues via the pull queue
API. Celery uses queues for interprocess communication and creates queues
dynamically for that purpose.

In the end though, using the pull queue for interprocess communication may not
be very performant anyway even if celery was supported. More research may be
needed to have full support for celery.
