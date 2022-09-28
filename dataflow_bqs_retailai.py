import apache_beam as beam
from apache_beam.runners import DataflowRunner
from apache_beam.options import pipeline_options
from apache_beam.options.pipeline_options import GoogleCloudOptions
from apache_beam.options.pipeline_options import WorkerOptions
from apache_beam.options.pipeline_options import SetupOptions
from apache_beam.options.pipeline_options import DebugOptions
import google.auth
import argparse
import logging



def create_sessions_list():
    from google.cloud import bigquery_storage_v1
    project_id='pod-fr-retail'
    client = bigquery_storage_v1.BigQueryReadClient()
    table = "projects/{}/datasets/{}/tables/{}".format(
          "pod-fr-retail", "demo", "test"
    )
    requested_session = bigquery_storage_v1.types.ReadSession()
    requested_session.table = table
    requested_session.data_format = bigquery_storage_v1.types.DataFormat.AVRO
    requested_session.read_options.selected_fields.append("orderId")
    #requested_session.read_options.row_restriction = 'state = "WA"'
    modifiers = None
    parent = "projects/{}".format(project_id)
    session = client.create_read_session(
        parent=parent,
        read_session=requested_session,
        max_stream_count=30,
    )

    readers=[]
    #print(session)
    for stream in session.streams:
        readers.append({'session':session,"streamName":stream.name})
    return readers


class bqstorage(beam.DoFn):
    def setup(self):
        print('hello')
    def process(self, element):
        from google.cloud import bigquery_storage_v1
        clientbq = bigquery_storage_v1.BigQueryReadClient()
        reader = self.clientbq.read_rows(element['streamName'])
        rows = reader.rows(element['session'])
        for row in rows:
            yield row


class retailAddLocalInventory(beam.DoFn):
    def process(self, element):
        t=element
        from googleapiclient.discovery import build
        retail=build('retail', 'v2alpha',static_discovery= False)
        productsCatalog = retail.projects().locations().catalogs().branches().products()
        product='projects/486742359899/locations/global/catalogs/default_catalog/branches/0/products/16684'
        local_inventory={
            "localInventories": [
                {
                      "placeId": 'store123',
                      "priceInfo": {
                          "currencyCode": 'USD',
                          "price": 1.23,
                          "originalPrice": 1.23
                      },
                      "attributes":{ 
                          "vendor": {"text": ["vendor1234", "vendor456"]}
                          ,"lengths_cm": {"numbers":[2.3, 15.4]}
                          , "heights_cm": {"numbers":[8.1, 6.4]} 
                      }
                 }
              ]
            ,"allowMissing": True
            ,"addMask": "attributes.vendor"
        }
        productsCatalog.addLocalInventories(product=product, body=local_inventory).execute()
        yield element



def run(argv=None):
    
    project='pod-fr-retail'
    zone='europe-west1-c'
    region='europe-west1'
    worker_machine_type='n1-standard-1' #g1-small
    num_workers=1
    max_num_workers=1
    temp_location = 'gs://pod-fr-retail-demo/temp'
    staging_location='gs://pod-fr-retail-demo/staging'

    # Setting up the Beam pipeline options.
    options = pipeline_options.PipelineOptions()
    #options.view_as(pipeline_options.StandardOptions).streaming = False
    _,options.view_as(GoogleCloudOptions).project = google.auth.default()
    options.view_as(GoogleCloudOptions).region = region
    options.view_as(GoogleCloudOptions).staging_location = staging_location
    options.view_as(GoogleCloudOptions).temp_location = temp_location
    options.view_as(WorkerOptions).worker_zone = zone
    options.view_as(WorkerOptions).machine_type = worker_machine_type
    options.view_as(WorkerOptions).num_workers = num_workers
    #options.view_as(WorkerOptions).max_num_workers = max_num_workers
    options.view_as(WorkerOptions).autoscaling_algorithm='NONE'
    options.view_as(SetupOptions).requirements_file='requirements.txt'
    #options.view_as(SetupOptions).save_main_session = True
    #options.view_as(DebugOptions).experiments = ['shuffle_mode=service,use_runner_v2']
    #options.view_as(SetupOptions).requirements_cache='/root/notebook/workspace/20200617'

    with beam.Pipeline(DataflowRunner(),options=options) as p:
        (p
         | "Create " >> beam.Create(create_sessions_list())
         | "Read orderId" >> beam.ParDo(bqstorage())
         | "Add or update Local inventory" >>  beam.ParDo(retailAddLocalInventory())
         #| ksdlk
        )
        
if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    run()