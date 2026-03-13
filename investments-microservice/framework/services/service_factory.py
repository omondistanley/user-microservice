from abc import ABC, abstractmethod


class BaseServiceFactory(ABC):
    @classmethod
    @abstractmethod
    def get_service(cls, service_name):
        raise NotImplementedError()
