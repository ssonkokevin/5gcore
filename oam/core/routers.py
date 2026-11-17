"""
Database Router for Multi-Database Support

Routes models to:
- srg_db (default): STP/DRA tables (tbl_stp_*, tbl_m3ua_*, tbl_dra_*)
- hssdb: UDM/HSS/HLR tables (tbl_subscriber, tbl_*_subscription, tbl_*_profile, etc.)
"""
from .models import (
    # STP/DRA -> default
    DRALocal, DRAPeerSet, DRAPeer, DRARoute, DRATranslate,
    M3UAGlobal, M3UALocal, M3UALinkset, M3UALink,
    STPRoute, STPTranslate,
    # Reference -> hssdb
    MCCMNC, PLMNProfile,
    # Subscriber -> hssdb
    Subscriber, AuthVector,
    # Subscriptions -> hssdb
    EPSSubscription, FiveGSubscription, IMSSubscription,
    # Profiles -> hssdb
    APNProfile, SupplementaryService, RoamingProfile,
    # Routing -> hssdb
    USSDRoute, CamelServiceProfile,
    # Network -> hssdb
    NetworkNode,
    # Batch -> hssdb
    BatchUpload, IMSIRange,
)


class DatabaseRouter:
    """Route models to appropriate database."""
    
    # Models that go to hssdb
    HSSDB_MODELS = {
        MCCMNC, PLMNProfile,
        Subscriber, AuthVector,
        EPSSubscription, FiveGSubscription, IMSSubscription,
        APNProfile, SupplementaryService, RoamingProfile,
        USSDRoute, CamelServiceProfile,
        NetworkNode,
        BatchUpload, IMSIRange,
    }
    
    # Models that go to default (srg_db)
    DEFAULT_MODELS = {
        DRALocal, DRAPeerSet, DRAPeer, DRARoute, DRATranslate,
        M3UAGlobal, M3UALocal, M3UALinkset, M3UALink,
        STPRoute, STPTranslate,
    }
    
    def db_for_read(self, model, **hints):
        """Suggest the database to read from."""
        if model in self.HSSDB_MODELS:
            return "hssdb"
        if model in self.DEFAULT_MODELS:
            return "default"
        return None
    
    def db_for_write(self, model, **hints):
        """Suggest the database to write to."""
        if model in self.HSSDB_MODELS:
            return "hssdb"
        if model in self.DEFAULT_MODELS:
            return "default"
        return None
    
    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations if both objects are in the same database."""
        db1 = self.db_for_read(obj1.__class__)
        db2 = self.db_for_read(obj2.__class__)
        if db1 and db2:
            return db1 == db2
        return None
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Control which models get migrated to which database."""
        if db == "hssdb":
            # Only allow HSSDB models to migrate to hssdb
            for model in self.HSSDB_MODELS:
                if model._meta.label_lower == f"core.{model_name}":
                    return True
            return False
        elif db == "default":
            # Only allow DEFAULT models to migrate to default
            for model in self.DEFAULT_MODELS:
                if model._meta.label_lower == f"core.{model_name}":
                    return True
            return False
        return None