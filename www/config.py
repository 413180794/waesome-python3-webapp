import config_default


class Dict(dict):
    # 扩展了一下dict的功能，x = Dict((1,2,3),(3,3,4),d="12",s="xd") ，这样是什么需求下的产物呢？
    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value


def merge(defaults, override):
    # 合并默认与覆盖
    r = {}
    for k, v in defaults.items():
        # 从默认字典中读取
        if k in override:  # 如果在覆盖字典中出现该键
            if isinstance(v, dict):  # 如果该键的值是字典
                r[k] = merge(v, override[k])
            else:
                r[k] = override[k]
        else:
            r[k] = v
    return r

def toDict(d):
    # 转一下类型，用意何在
    # 为了实现 x.d替换成x[d]
    D = Dict()
    for k,v in d.items():
        D[k] = toDict(v) if isinstance(v,dict) else v
    return D

configs = config_default.configs

try:
    import config_override
    configs = merge(configs,config_override.configs)
except ImportError:
    pass

configs = toDict(configs)

