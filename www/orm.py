import logging

import aiomysql as aiomysql


def log(sql, args=()):
    logging.info("SQL:%s" % sql)


async def create_pool(loop, **kw):  # 创建连接池， 其中__pool是全局变量,异步创建数据库连接池，等待调用
    '''
    class Pool:  返回的实例是一个连接池。创建池后，最小有minsize个连接可以使用，并且可以最大增加到maxsize
    '''
    logging.info('create database connection pool...')
    global __pool
    __pool = await aiomysql.create_pool(
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        loop=loop,
    )


'''
aiomysql.create_pool -> 创建与mysql数据库的连接池的协程

'''


async def select(sql, args, size=None):
    log(sql, args)
    global __pool
    async with __pool.get() as conn:  # 异步从数据库中取得一个连接
        async with conn.cursor(aiomysql.DictCursor) as cur:  # class DictCuror : 将结果作为字典返回的游标，所有方法和参数与Cursor相同
            await cur.execute(sql.replace("?", "%s"), args or ())
            # 协程，用给定参数替换任何标记执行给定的操作 例如 await cursor.execute("SELECT * FROM t1 WHERE id=%s",(5,)
            if size:
                rs = await cur.fetchmany(size)  # 如果指定了size，则获取指定size个数据
            else:
                rs = await cur.fetchall()  # 如果没有指定size，则获取全部数据。
        logging.info("rows returned: %s" % len(rs))
        return rs


async def execute(sql, args, autocommit=True):
    log(sql)
    global __pool  # 取得连接池
    async with __pool.get() as conn:  # 从连接池中获得一条数据
        if not autocommit:  # 如果不允许自动提交
            await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?', "%s"), args)
                affected = cur.rowcount
            if not autocommit:
                await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.rollback()
            raise
        return affected


def create_args_string(num):
    # '?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?' 创建一些问号
    L = []
    for n in range(num):
        L.append("?")
    return ', '.join(L)


class Field(object):
    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type  # 每一列的类型
        self.primary_key = primary_key  # 主键
        self.default = default  # 默认？用来做什么？ - - > 默认值

    def __str__(self):
        return "<%s,%s:%s>" % (self.__class__.__name__, self.column_type, self.name)


class StringField(Field):  # 继承Field
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super(StringField, self).__init__(name, ddl, primary_key, default)


class BooleanField(Field):
    def __init__(self, name=None, default=False):
        super(BooleanField, self).__init__(name, "boolean", False, default)


class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super(IntegerField, self).__init__(name, 'bigint', primary_key, default)


class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0.0):
        super(FloatField, self).__init__(name, 'real', primary_key, default)


class TextField(Field):
    def __init__(self, name=None, default=None):
        super(TextField, self).__init__(name, 'text', False, default)


# __new__()方法接收到的参数依次是：
# 1. 当前准备创建的类的对象。
# 2. 类的名字
# 3. 类继承的父类集合
# 4. 类的方法集合

class ModelMetaclass(type):  # 定义元类
    def __new__(cls, name, bases, attrs):
        if name == "Model":
            return type.__new__(cls, name, bases, attrs)  # 不去修改名为Model的类
        tableName = attrs.get("__table__",
                              None) or name  # 表名字是tablbName，如果该类中有__table__变量名，则令tableName = __table__,或者tableName = 类名
        logging.info("found model:%s(table : %s)" % (name, tableName))
        mappings = dict()  # 保存所有的类的变量名和对应的值。
        fields = []  # 这个列表做什么的？
        primaryKey = None  # 是否存在主键
        for k, v in attrs.items():  # 遍历类的方法集合
            if isinstance(v, Field):  # 如果该变量的属性属于Field
                logging.info("    found mapping:%s ==> %s" % (k, v))
                mappings[k] = v  # 将变量与值存在字典中
                if v.primary_key:
                    # 如果在变量是主键
                    if primaryKey:  # 主键已经存在了。
                        raise AttributeError("Duplicate primary key for field:%s", k)
                    primaryKey = k
                else:
                    fields.append(k)  # 除了主键外的属性名保存在fields
        if not primaryKey:  #
            raise AttributeError("Primary key not found")
        for k in mappings.keys():
            attrs.pop(k)  # 将类变量删除，实例变量如果和类变量重复，那么实例变量就会覆盖类变量。
        escaped_fields = ["`" + s + "`" for s in fields]  # 除了主键外的属性名两端加上 反引号
        # 反引号的作用
        # 它是为了区分MYSQL的保留字与普通字符而引入的符号。

        attrs['__mappings__'] = mappings  # 保存属性与列的映射关系
        attrs['__table__'] = tableName  # 保存表的名字
        attrs['__primary_key__'] = primaryKey  # 主键属性名
        attrs['__fields__'] = fields  # 除了主键外的属性名

        attrs['__select__'] = f"SELECT `{primaryKey}`,{', '.join(escaped_fields)} from `{tableName}`"
        # 该句sql语言的意思是：查询tableName表中所有列的数据
        attrs['__insert__'] = f"INSERT INTO `{tableName}` ({', '.join(escaped_fields)}, `{primaryKey}`) VALUES({create_args_string(len(escaped_fields) + 1)})"
        # 该句sql语言的意思是：向tableName表中插入一行。
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (
            tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)),
            primaryKey)  # 更新表中主键是primaryKey的一行。
        # map函数没有看懂
        print(attrs['__update__'])
        attrs['__delete__'] = f'delete from `{tableName}` WHERE `{primaryKey}`=?'
        # 该句sql语言的意思是：从tableName表中删除主键为primaryKey的一行

        return type.__new__(cls, name, bases, attrs)


class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kwargs):
        super(Model, self).__init__(**kwargs)

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(f"'model' object has no attribute '{item}'")

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):  # 封装了一层查询
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:  # 这里为什么要考虑default是函数？ 因为默认值可以是一个函数的返回值
                value = field.default() if callable(field.default) else field.default
                logging.debug("using default value for %s: %s" % (key, str(value)))
                setattr(self, key, value)
        return value

    @classmethod
    async def findAll(cls, where=None, args=None, **kw):
        sql = [cls.__select__]  # 利用列表拼接字符串
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:  # 如果没有参数
            args = []
        orderBy = kw.get("orderBy", None)  # 是否需要排序
        if orderBy:  # 需要排序
            sql.append('order by')
            sql.append(orderBy)
        limit = kw.get('limit', None)  # 是否有查询限制
        if limit is not None:  # 如果有查询限制
            sql.append("limit")
            if isinstance(limit, int):  # 如果limit是一个整数
                sql.append("?")
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append("?,?")
                args.extend(limit)  # list.extend(seq) extend()函数用于在列表末尾一次性追加另一个序列中的多个值（用新列表扩展原来的列表）
            else:
                raise ValueError("Invalid limit value: %s " % str(limit))
        rs = await select(" ".join(sql),args) # 返回查询结果
        return [cls(**r) for  r in rs] # 返回查询结果的实例

    @classmethod
    async def findNumber(cls,selectField,where=None,args=None):
        '''利用select和where,找到指定列的个数'''
        sql = [f"SELECT COUNT({selectField}) _num_ FROM `{cls.__table__}`"]
        if where :
            sql.append("where")
            sql.append(where)
        rs = await select (" ".join(sql),args,1)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']

    @classmethod
    async def find(cls,pk):
        " 通过主键找到某对象"
        rs = await select("%s where `%s`=?" %(cls.__select__,cls.__primary_key__),[pk],1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    async def save(self):
        args = list(map(self.getValueOrDefault,self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__,args)
        if rows!=1:
            logging.warn("failed to insert record:affected rows: %s" % rows)

    async def update(self):
        args = list(map(self.getValue,self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__,args)
        if rows!=1:
            logging.warn("failed to update by primary key: affected rows: %s"%rows)

    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__,args)
        if rows != 1:
            logging.warn("failed to remove by primary key: affected rows: %s" %rows)


