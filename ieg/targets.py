import sys
import json
import threading
from kafka import KafkaProducer
from confluent_kafka import Producer

class TargetStdout:
    """
    Outputs generated records to the standard output (console).
    Thread-safe implementation to ensure proper handling of concurrent writes.
    """
    lock = threading.Lock()

    def print(self, record):
        with self.lock:
            print(str(record))
            sys.stdout.flush()

    def __str__(self):
        return '#TargetStdout()'

class TargetFile:
    """
    Outputs generated records to a specified file.
    """
    f = None

    def __init__(self, file_name):
        self.file_name = file_name
        self.f = open(file_name, 'w')

    def __str__(self):
        return 'TargetFile(file_name='+self.file_name+')'

    def print(self, record):
        self.f.write(str(record)+'\n')
        self.f.flush()

class TargetKafka:
    """
    Sends generated records to a Kafka topic.
    """
    producer = None
    topic = None

    def __init__(self, endpoint, topic, security_protocol, compression_type, topic_key):
        self.endpoint = endpoint
        self.producer = KafkaProducer(
            bootstrap_servers=endpoint,
            security_protocol=security_protocol,
            compression_type=compression_type
        )
        self.topic = topic
        self.topic_key = topic_key

    def __str__(self):
        return 'TargetKafka(endpoint='+self.endpoint+', topic='+self.topic+', topic_key='+self.topic_key+')'

    def print(self, record):
        if len(self.topic_key) == 0:
            self.producer.send(topic=self.topic, value=bytes(record, 'utf-8'))
        else:
            key = ''
            json_record = json.loads(record)
            for dim in self.topic_key:
                key += json_record[dim]
            self.producer.send(topic=self.topic, value=bytes(record, 'utf-8'), key=bytes(key, 'utf-8'))
        self.producer.flush()

class TargetConfluent:
    """
    Sends generated records to a Confluent Kafka topic with SASL authentication.
    """
    producer = None
    topic = None
    username = None
    password = None

    def __init__(self, servers, topic, username, password, topic_key):
        self.servers = servers
        self.producer = Producer({
            'bootstrap.servers': servers,
            'sasl.mechanisms': 'PLAIN',
            'security.protocol': 'SASL_SSL',
            'sasl.username': username,
            'sasl.password': password
        })
        self.topic = topic
        self.username = username
        self.password = password
        self.topic_key = topic_key

    def __str__(self):
        return 'TargetConfluent(servers='+self.servers+', topic='+self.topic+', username='+self.username+', password='+self.password+', topic_key='+self.topic_key+')'

    def print(self, record):
        if len(self.topic_key) == 0:
            self.producer.produce(topic=self.topic, value=str(record))
        else:
            key = ''
            json_record = json.loads(record)
            for dim in self.topic_key:
                key += json_record[dim]
            self.producer.produce(topic=self.topic, value=str(record), key=key)
        self.producer.flush()
