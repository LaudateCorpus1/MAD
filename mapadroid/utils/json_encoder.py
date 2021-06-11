import json
from datetime import timezone, datetime
from decimal import Decimal
from enum import Enum

from mapadroid.db.model import Base
from mapadroid.mad_apk.apk_enums import APKArch, APKType
from mapadroid.mad_apk.custom_types import MADapks, MADPackage, MADPackages


class MADEncoder(json.JSONEncoder):
    def apk_encode(self, object_to_encode):
        if isinstance(object_to_encode, MADapks) or isinstance(object_to_encode, MADPackages):
            updated = {}
            for obj_key, key_value in object_to_encode.items():
                updated[str(obj_key.name)] = self.apk_encode(key_value)
            object_to_encode = updated
        return object_to_encode

    def encode(self, object_to_encode, *args, **kw):
        for_json = object_to_encode
        if isinstance(object_to_encode, MADapks) or isinstance(object_to_encode, MADPackages):
            for_json = self.apk_encode(object_to_encode)
        return super(MADEncoder, self).encode(for_json, *args, **kw)

    def default(self, obj):
        if isinstance(obj, MADPackage):
            return obj.get_package(backend=False)
        elif isinstance(obj, APKArch):
            return obj.value
        elif isinstance(obj, APKType):
            return obj.value
        elif isinstance(obj, MADapks):
            return json.JSONEncoder.default(self, obj)
        elif isinstance(obj, type):
            return str(obj)
        elif isinstance(obj, datetime):
            return obj.replace(tzinfo=timezone.utc).timestamp()
        elif isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, Enum):
            return obj.value
        elif isinstance(obj, Base):
            # Dumb serialization of a model class to json... excluding private/protected attributes
            return {var: val for var, val in vars(obj).items() if not var.startswith("_")}
        return json.JSONEncoder.default(self, obj)
