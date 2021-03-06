from datetime import datetime
from functools import wraps
from inspect import signature

from bson.errors import InvalidId
from bson.objectid import ObjectId
from cerberus import TypeDefinition, Validator
from sanic.exceptions import InvalidUsage, NotFound
from sanic.request import File, Request


class CustomValidator(Validator):
    # Types
    types_mapping = Validator.types_mapping.copy()
    types_mapping['file'] = TypeDefinition('file', (File,), ())
    types_mapping['datetime'] = TypeDefinition('datetime', (datetime,), ())
    types_mapping['object_id'] = TypeDefinition('object_id', (ObjectId,), ())

    def __init__(self, *args, **kwargs):
        self.request = kwargs['request']
        super(CustomValidator, self).__init__(*args, **kwargs)

    # Checks
    def _check_with_ip_address_validator(self, field, value):
        import socket
        try:
            socket.inet_aton(value)
        except socket.error:
            self._error(field, "Malformed IP address")

    # Coerce
    def _normalize_coerce_json(self, value):
        from json import loads
        return loads(value)

    def _normalize_coerce_first(self, value):
        return value[0]

    def _normalize_coerce_object_id(self, value):
        return ObjectId(value)

    def _normalize_coerce_empty_or_object_id(self, value):
        return ObjectId(value) if len(value) else value

    def _normalize_coerce_boolean(self, value):
        if isinstance(value, str):
            return value.lower() in ('true', '1')
        return True if value else False

    def _normalize_coerce_integer(self, value):
        return int(value)

    def _normalize_coerce_float(self, value):
        return float(value)

    # Validates
    def _validate_check_existence(self, check_existence, field, value):
        """ Tests the existence of a mongo id against a collection.
        {'check_existence': {
            'name': 'profiles',
            'lookup': True,
            'map': {
                'profiles': {
                    'name': 'profiles',
                    'not_found': 'User not found'
                }
            }
        }}
        The rule's arguments are validated against this schema:
        {'type': 'string'}
        """
        if 'lookup' in check_existence and check_existence['lookup']:
            check_existence['name'] = self._lookup_field(check_existence['name'])[1]

        collection_metadata = check_existence['map'][check_existence['name']]
        if not self.request.app.dependencies.get_component('document_exists')(collection_metadata['name'], value):
            self._error(field, collection_metadata['not_found'])

    def _validate_allowed_path(self, allowed_path, field, value):
        """ Tests the validity of the string and raises a not found error if it is invalid.
        {'allowed_path': ['likes', 'views']}
        The rule's arguments are validated against this schema:
        {'type': 'string'}
        """
        if isinstance(allowed_path, str):
            allowed_path = [allowed_path]
        
        if value not in allowed_path:
            if self.request:
                raise NotFound('Requested URL {} not found'.format(self.request.path))
            else:
                raise NotFound('Requested URL not found')

    def _validate_allowed_content_type(self, allowed_content_type, field, value):
        """ Tests the content type of a file.
        {'allowed_content_type': 'image/jpeg'}
        The rule's arguments are validated against this schema:
        {'type': 'string'}
        """
        if value.type not in allowed_content_type:
            self._error(field, "Content type not allowed")

    # Default setters
    def _normalize_default_setter_array_wrap(self, document):
        return [document]

    def _normalize_default_setter_timestamp(self, document):
        from time import time
        return [str(int(time()))]

class ValidatePath(object):
    def __init__(self, schema: dict):
        self.schema = schema

    def __call__(self, function):
        @wraps(function)
        async def wrapper(request, *args, **kwargs):
            validator = CustomValidator(request=request, schema=self.schema, allow_unknown=True)
            
            if not validator.validate(kwargs):
                raise InvalidUsage(validator.errors)

            return await function(request, *args, **validator.document)

        return wrapper

class ValidateRequest(object):
    def __init__(self, schema: dict, request_property: str):
        self.schema = schema
        self.request_property = request_property

    def __call__(self, function):
        @wraps(function)
        async def wrapper(request, *args, **kwargs):
            validator = CustomValidator(request=request, schema=self.schema, purge_unknown=True)
            
            document = getattr(request, self.request_property, {})
            document = dict(document) if document else {}
            
            if not validator.validate(document):
                raise InvalidUsage(validator.errors)

            validated = kwargs.get('validated', {})
            validated[self.request_property] = validator.document
            kwargs['validated'] = validated

            return await function(request, *args, **kwargs)

        return wrapper

class Validate(object):
    def __init__(self, schema: dict, request_property: str):
        self.schema = schema
        self.request_property = request_property

    def __call__(self, function):
        @wraps(function)
        async def wrapper(request, *args, **kwargs):
            validator = CustomValidator(request=request, schema=self.schema, purge_unknown=True)

            document = getattr(request, self.request_property, {})
            document = dict(document) if document else {}

            if not validator.validate(document):
                raise InvalidUsage(validator.errors)

            if self.request_property in signature(function).parameters:
                kwargs[self.request_property] = validator.document

            return await function(request, *args, **kwargs)

        return wrapper
