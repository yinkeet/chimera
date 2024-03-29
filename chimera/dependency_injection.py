import pkgutil
from functools import wraps
from inspect import signature, iscoroutinefunction
from typing import Any, cast, get_type_hints

from sanic.log import logger


def get_component(app, name):
    return app.ctx.dependencies.get_component(name)

class Dependencies(object):
    def __init__(self, app, loop):
        self.app = app
        self.loop = loop
        self.__components = {}
        self.app.ctx.dependencies = self

    async def register_package(self, package):
        logger.debug('Register package \'' + package.__name__ + '\'')
        for importer, module_name, is_pkg in pkgutil.iter_modules(package.__path__, prefix=package.__name__ + "."):
            if not is_pkg:
                module = importer.find_module(module_name).load_module(module_name)
                for attr in dir(module):
                    instance = getattr(module, attr)
                    if(issubclass(type(instance), Register)):
                        logger.debug('Register component \'' + module.__name__ + '.' + attr + '\' as ' + instance.name)
                        await self._register(instance)

    async def register_module(self, module):
        for attr in dir(module):
            instance = getattr(module, attr)
            if(issubclass(type(instance), Register)):
                logger.debug('Register component \'' + module.__name__ + '.' + attr + '\' as ' + instance.name)
                await self._register(instance)

    def register(self, name, object):
        logger.debug('Register component ' + name)
        self.__components[name] = object

    def get_component(self, name):
        logger.debug('Get component \'' + name + '\'')
        return self.__components[name]

    def exists(self, name):
        return name in self.__components

    async def _register(self, instance):
        parameters = signature(instance.function).parameters
        kw = {}
        if 'app' in parameters:
            kw['app'] = self.app
        if 'loop' in parameters:
            kw['app'] = self.loop
        if iscoroutinefunction(instance.function):
            self.__components[instance.name] = await instance.function(**kw)
        else:
            self.__components[instance.name] = instance.function(**kw)

class Register(object):
    def __init__(self, name):
        self.name = name

    def __call__(self, function):
        self.function = function
        return self

def inject(function):
    @wraps(function)    
    async def wrapper(request, *args, **kwargs):
        for parameter in signature(function).parameters:
            dependencies = request.app.ctx.dependencies
            if dependencies.exists(parameter):
                kwargs[parameter] = dependencies.get_component(parameter)

        return await function(request, *args, **kwargs)
    return wrapper
