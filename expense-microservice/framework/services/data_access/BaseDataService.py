from abc import ABC, abstractmethod


class DataDataService(ABC):

    def __init__(self, context):
        self.context = context

    @abstractmethod
    def _get_connection(self):
        raise NotImplementedError("Abstract method _get_connection()")

    @abstractmethod
    def get_data_object(self,
                        database_name: str,
                        collection_name: str,
                        key_field: str,
                        key_value: str):
        raise NotImplementedError("Abstract method get_data_object()")
