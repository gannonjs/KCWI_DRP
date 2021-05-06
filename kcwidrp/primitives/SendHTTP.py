import os
import requests
import time

from keckdrpframework.primitives.base_primitive import BasePrimitive
from kcwidrp.primitives.kcwi_file_primitives import kcwi_fits_writer, \
                                                    kcwi_fits_reader, \
                                                    strip_fname


class SendHTTP(BasePrimitive):

    def __init__(self, action, context):
        BasePrimitive.__init__(self, action, context)
        self.logger = context.pipeline_logger
    
    def _pre_condition(self):
        self.user = self.config.instrument.rti_user
        self.pw = self.config.instrument.rti_pass
        if self.user == '' or self.pw == '':
            self.logger.error("Username or password is not set for RTI access")
            return False
        return True

    def _perform(self):

        if not self.action.args.ccddata.header['KOAID']:
            self.logger.error(f"Encountered a file with no KOA ID: {self.action.args.name}")
            return self.action.args
        
        data_directory = os.path.join(self.config.instrument.cwd,
                                      self.config.instrument.output_directory)
        
        self.logger.info(f"Alerting RTI that {strip_fname(self.action.args.name)} is ready for ingestion")

        url = self.config.instrument.rti_url
        data = {
            'instrument': 'KCWI',
            'koaid': self.action.args.ccddata.header['KOAID'],
            'ingesttype': 'lev2',
            'datadir': str(data_directory),
            'start': str(self.action.args.ingest_time),
            'reingest': True,
            'testonly': True,
            'dev': True
        }
        
        attempts = 0
        limit = self.config.instrument.rti_attempts
        while attempts < limit:
            res = self.get_url(url, data)
            if res is None:
                t = self.config.instrument.rti_retry_time
                attempts += 1
                self.logger.error(f"Waiting {t} seconds to attempt again... ({attempts}/{limit})")
                time.sleep(t)
            else:
                self.logger.info(f"Post returned status code {res.status_code}")
                return self.action.args
        
        self.logger.error(f"Post attempted {limit} times and got no response.")
        self.logger.error("Aborting.")
        return self.action.args
    
    def get_url(self, url, data):
        try:
            self.logger.info(f"GET to RTI with KOAID {data['koaid']}")
            res = requests.get(url, params = data, auth=(
                                                        self.user,
                                                        self.pw
                                                        ))
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error caught while posting to {url}:")
            self.logger.error(e)
            return None
        return res
