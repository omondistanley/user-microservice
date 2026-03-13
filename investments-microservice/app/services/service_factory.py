from app.core.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
)
from app.resources.holding_resource import HoldingResource
from app.services.holdings_data_service import HoldingsDataService
from app.services.portfolio_snapshot_service import PortfolioSnapshotDataService
from app.services.risk_profile_service import RiskProfileDataService
from app.services.recommendation_data_service import RecommendationDataService
from framework.services.service_factory import BaseServiceFactory


class ServiceFactory(BaseServiceFactory):
    @classmethod
    def get_service(cls, service_name: str):
        if service_name == "HoldingResource":
            res = HoldingResource(config=None)
            res.data_service = cls.get_service("HoldingsDataService")  # type: ignore
            return res
        if service_name in {
            "HoldingsDataService",
            "PortfolioSnapshotDataService",
            "RiskProfileDataService",
            "RecommendationDataService",
        }:
            context = {
                "user": DB_USER or "postgres",
                "password": DB_PASSWORD or "postgres",
                "host": DB_HOST or "localhost",
                "port": int(DB_PORT) if DB_PORT else 5432,
                "dbname": DB_NAME or "investments_db",
            }
            if service_name == "HoldingsDataService":
                return HoldingsDataService(context=context)
            if service_name == "PortfolioSnapshotDataService":
                return PortfolioSnapshotDataService(context=context)
            if service_name == "RiskProfileDataService":
                return RiskProfileDataService(context=context)
            if service_name == "RecommendationDataService":
                return RecommendationDataService(context=context)
        return None
