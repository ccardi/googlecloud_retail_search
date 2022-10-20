import apache_beam as beam
from apache_beam.runners import DataflowRunner
from apache_beam.runners import DirectRunner
from apache_beam.options import pipeline_options
from apache_beam.options.pipeline_options import GoogleCloudOptions
from apache_beam.options.pipeline_options import WorkerOptions
from apache_beam.options.pipeline_options import SetupOptions
from apache_beam.options.pipeline_options import DebugOptions
import argparse
import logging

def create_bqs_session(project_id, dataset_id, table_id):
    from google.cloud import bigquery_storage_v1
    client = bigquery_storage_v1.BigQueryReadClient()
    requested_session = bigquery_storage_v1.types.ReadSession()
    requested_session.table =  "projects/{}/datasets/{}/tables/{}".format(
          project_id, dataset_id, table_id
    )
    requested_session.data_format = bigquery_storage_v1.types.DataFormat.AVRO
    requested_session.read_options.selected_fields = ["orderId"]
    session = client.create_read_session(
        parent="projects/{}".format(project_id),
        read_session=requested_session,
        max_stream_count=300,
    )
    stream_names=[]
    for stream in session.streams:
        stream_names.append(stream.name)
    return  stream_names

class ReadBQstorage(beam.DoFn):
    def setup(self):
        from google.cloud import bigquery_storage_v1
        self.clientbq = bigquery_storage_v1.BigQueryReadClient()
    def process(self, element):
        logging.info('Stream to read: %s', element)
        reader = self.clientbq.read_rows(element)
        rows = reader.rows()
        for row in rows:
            yield row


class retailAddLocalInventory(beam.DoFn):
    def setup(self):
        from google.cloud import retail_v2
        self.client = retail_v2.ProductServiceClient()
        self.LocalInventory=retail_v2.LocalInventory
        self.PriceInfo=retail_v2.PriceInfo
        self.AddLocalInventoriesRequest=retail_v2.AddLocalInventoriesRequest
    def process(self, element):
        row=element
        print(element)
        # Initialize request argument(s)
        request = self.AddLocalInventoriesRequest(
            product="projects/486742359899/locations/global/catalogs/default_catalog/branches/1/products/16684",
            local_inventories= [ 
                self.LocalInventory( 
                    place_id= element["orderId"]
                    , price_info= self.PriceInfo(
                        currency_code= 'USD',
                        price = 1.25,
                        original_price=1.26
                    ))
            ]
        )
        # Make the request
        operation = self.client.add_local_inventories(request=request, timeout=200)
        yield element



def run(argv=None):
    # Setting up the Beam pipeline options.
    options = pipeline_options.PipelineOptions()
    #options.view_as(GoogleCloudOptions).job_name = 'read-bq-test'
    options.view_as(GoogleCloudOptions).project = 'pod-fr-retail'
    options.view_as(GoogleCloudOptions).region = 'europe-west1'
    options.view_as(GoogleCloudOptions).staging_location = 'gs://pod-fr-retail/bqdataflow/staging'
    options.view_as(GoogleCloudOptions).temp_location = 'gs://pod-fr-retail/bqdataflow/temp'
    #options.view_as(WorkerOptions).max_num_workers = 30
    options.view_as(SetupOptions).requirements_file='requirements.txt'
    #options.view_as(DebugOptions).experiments = ["no_use_multiple_sdk_containers"]
    sessions = create_bqs_session('pod-fr-retail', 'demo', 'test')
    with beam.Pipeline(DataflowRunner(),options=options) as p:
        (p
         | "Create " >> beam.Create(sessions, reshuffle=True)
         | "Read orderId" >> beam.ParDo(ReadBQstorage())
         | "Add Local inventories orderId" >> beam.ParDo(retailAddLocalInventory())
        )


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    run()