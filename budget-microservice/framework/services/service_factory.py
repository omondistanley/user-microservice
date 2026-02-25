from abc import ABC, abstractmethod


class BaseServiceFactory(ABC):

    def __init__(self):
        pass

    @classmethod
    @abstractmethod
    def get_service(cls, service_name):
        raise NotImplementedError()
