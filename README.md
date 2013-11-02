kombu-appengine-pullqueue
=========================

A kombu backend for the appengine pull queue API. This can be used to create
consumers for tasks from the appengine pull queue API. 

You can find out more about the pull task queue REST API here:
https://developers.google.com/appengine/docs/python/taskqueue/rest/

Why Use It
=======================

Why use the pull task queue API?

There are some instances where you would like to use the pull queue API to
perform tasks that are difficult or impossible to do on App Engine. Things
like complicated processing of images or video, using libraries or software
not available on App Engine, or long running CPU bound tasks.

Why use kombu?

kombu provides a pretty simple API for dealing with queues so it gives you
a good starting point for creating a consumer that can process tasks. Kombu
handles polling, routing, and management of tasks. And in the unlikely event
you want to use some other queue system you can reuse your existing code by
changing just a few options.

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

```python
from kombu import Connection

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
```

Here we use the SimpleQueue class from kombu. SimpleQueue has a very similar
api to the native Queue class in python. This producer will create a new tasks
on the task queue with a very simple JSON payload.

A Simple Consumer
=======================

A "consumer" processes tasks from the task queue and removes them once it is
finished processing.

```python
from kombu import Connection

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
```

We lease the task using the get() method and process it. In this case we are
simply printing the text message we received. After we are finished, we
"acknowledge" we are finished by calling the ack() method on the returned
message object. This deletes the task from the App Engine pull queue.

More Advanced Producers and Consumers
===========================================

More advanced routing can be done using kombu's Producer and Consumer classes.
Unless you are utilizing multiple pull queues and doing some complicated
routing, you likely wouldn't need to do use these.

If you are queueing tasks from an App Engine application, then you will likely
be using the App Engine SDK to queue your tasks anyway.

If you think you might need to do something complicated like use multiple
queues with tasks processed by a single or multiple consumer then you should
probably check out the documentation for kombu.
http://ask.github.io/kombu/introduction.html#terminology

```python
from kombu import Connection, Exchange, Queue

# Create the exchange and queue. These are used to route messages.
app_engine = Exchange("appengine", "direct", durable=True)
pull_queue = Queue("pull-queue", exchange=app_engine, routing_key="pull-queue")

conn = Connection(
    hostname='',
    userid='credentials',
    transport="kombu_appengine:Transport",
    transport_options={
        'project_name': 'my_project',
        'polling_interval': 5,
        'credentials_file': 'credentials',
    }
)

# Enqueue a task
text = "Hello World!"

with conn:
    # Declare the queue.
    pull_queue(conn.channel()).declare()

    with conn.Producer(exchange=app_engine, routing_key="pull-queue") as producer:
        producer.publish({'text': text})


    def process_msg(body, message):
        print body['text']
        # Acknowledge the message so the task is deleted
        message.ack()

    with conn.Consumer(video_queue, callbacks=[process_media]) as consumer:
        # Process messages and handle events on all channels
        while True:
            conn.drain_events()
```

Supported Transport Options
=============================

The kombu\_appengine transport backend supports several options which can be
set via the transport\_options parameter to the Connection class.

| Option            | Required | Default | Description                                                              |
| ----------------- |:--------:|:-------:|:------------------------------------------------------------------------:|
| project\_name     | required | None    | The Google Cloud Console project                                         |
| hrd\_project      | optional | True    | A boolean option specifying if the app is an HRD app in App Engine. This is used as a workaround for API issues. See this issue for details: https://code.google.com/p/googleappengine/issues/detail?id=10199 |
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
