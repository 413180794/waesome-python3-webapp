import asyncio, os, inspect, logging, functools

from urllib import parse
from aiohttp import web
from apis import APIError


def get(path):
    '''
    Define decorator @get('/path')
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            print(args)
            print(kw)
            return func(*args, **kw)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator


def post(path):
    # 修饰函数，为其增加两个私有变量 __method__、__route__

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper.__method__ = "POST"
        wrapper.__route__ = path
        return wrapper

    return decorator


def get_required_kw_args(fn):
    # 返回关键字参数，并且关键字参数默认值为空的参数名称
    args = []
    params = inspect.signature(fn).parameters  # 返回函数签名的有序的参数列表
    print(params)
    for name, param in params.items():
        # KEYWORD_ONLY 值必须作为关键字参数提供，仅仅关键字参数是出现在Python函数定义中的*或*args条目之后的参数。
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)


def get_named_kw_args(fn):
    # 返回关键字参数
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        # KEYWORD_ONLY 值必须作为关键字参数提供，仅仅关键字参数是出现在Python函数定义中的*或*args条目之后的参数。
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)


def has_named_kw_args(fn):
    # 判断某函数是否含有关键字参数
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True


def has_var_kw_arg(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        # VAR_KEYWORD =>  关键字参数的字典，未绑定到任何其他参数，这对应于Python函数定义中的**kwargs参数
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True


def has_request_arg(fn):
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == "request":
            found = True
            continue
        # VAR_POSITIONAL 一个为绑定到任何其他参数的位置参数元祖。这对应于Python函数定义中的*args参数。
        # 下面一句话的意思是：不允许request参数后有其他有名的参数。 -- 为什么要这样做呢？
        if found and (
                param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError(
                "request parameter must be the last named parameter in function: %s%s" % (fn.__name__, str(sig)))
        return found

# 这里以下，基本没有看懂什么意思。先放在这里，日后在梳理。


class RequestHandler(object):
    # RequestHandler目的就是从URL函数中分析其需要接受的参数，从request中获取必要的参数，调用URL函数，然后把结果转换为web.Response对象，
    # 这样，就完全符合aiohttp框架的要求。
    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_arags = has_named_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    async def __call__(self, request): # RequestHandler是一个类，由于定义了__call__()方法，因此可以将其实例视为函数。
        # 这个函数基本没有看懂在干什么、。
        kw = None
        if self._has_var_kw_arg or self._has_named_kw_arags or self._required_kw_args:
            if request.method == "POST":
                if not request.content_type:
                    return web.HTTPBadRequest("Missing Content-Type")
                ct = request.content_type.lower()
                if ct.startswith("application/json"):  # 以application/json开头
                    params = await request.json()
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest("JSON body must be object")
                    kw = params
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith(
                        'multipart/form-data'):  # 什么意思？
                    params = await request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest("Unsupported Content-Type:%s" % request.content_type)
            if request.method == "GET":
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k, v in parse.parse_qs(qs, True).items():  # 这是在干什么？
                        kw[k] = v[0]
        if kw is None:
            kw = dict(**request.match_info)
        else:
            if not self._has_var_kw_arg and self._named_kw_args:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            for k, v in request.match_info.items():
                if k in kw:
                    logging.warning('Duplicate arg name in named arg and kw args:%s' % k)
                kw[k] = v
        if self._has_request_arg:
            kw['request'] = request
        if self._required_kw_args:
            for name in self._required_kw_args:
                if name not in kw:
                    return web.HTTPBadRequest("Missing argument:%s" % name)
        logging.info('call with args:%s' % str(kw))
        try:
            r = await self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)


def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static("/static/", path)
    logging.info("add static %s=>%s" % ("/static/", path))


def add_route(app, fn):
    # 用来注册一个URL处理函数
    method = getattr(fn, "__method__", None)
    path = getattr(fn, "__route__", None)
    if path is None or method is None:
        raise ValueError("@get or @post not defined in %s." % str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info(
        "add route %s %s => %s(%s)" % (method, path, fn.__name__, ",".join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method,path,RequestHandler(app,fn))

def add_routes(app,module_name):
    n = module_name.rfind(".")
    if n == (-1):
        mod = __import__(module_name,globals(),locals()) # 这是在干什么？__import__函数用来干什么？
    else:
        name = module_name[n+1:]
        mod = getattr(__import__(module_name[:n],globals(),locals(),[name]),name)
    for attr in dir(mod): # dir函数是什么？
        if attr.startswith("_"):
            continue
        fn = getattr(mod,attr)
        if callable(fn):
            method = getattr(fn,"__method__",None)
            path = getattr(fn,"__route__",None)
            if method and path:
                add_route(app,fn)



if __name__ == '__main__':
    def test(a, b, c="123", d="213", *args, dd, **kwargs):
        return None


    print(get_required_kw_args(test))
    print(get_named_kw_args(test))
    print(has_var_kw_arg(test))
