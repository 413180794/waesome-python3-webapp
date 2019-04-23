import json, logging, inspect, functools


# 这个文件，自定义了一些错误
class APIError(Exception):
    def __init__(self, error, data="", message=""):
        super(APIError, self).__init__(message)
        self.error = error
        self.data = data
        self.message = message


class APIValueError(APIError):
    def __init__(self, field, message=""):
        super(APIValueError, self).__init__("value:invalid", field, message)


class APIResourceNotFoundError(APIError):
    def __init__(self, field, message=""):
        super(APIResourceNotFoundError, self).__init__("Value:notfound", field, message)


class APIPermissionError(APIError):
    def __init__(self, message=""):
        super(APIPermissionError, self).__init__("permission:forbidden", "permission", message)


class Page(object):

    def __init__(self, item_count, page_index=1, page_size=10):
        self.item_count = item_count       # 总共多少个
        self.page_size = page_size         # 每页的大小
        self.page_count = item_count // page_size + (1 if item_count % page_size > 0 else 0)    # 总页数
        if item_count == 0 or page_index > self.page_count:          # 如果总共0个或者指定的页数大过了总页数，那么回到第一页
            self.offset = 0                # 偏移地址
            self.limit = 0                 # 一页数量
            self.page_index = 1            # 第一页
        else:
            self.page_index = page_index                    # 指定第几页
            self.offset = self.page_size * (page_index - 1) # 计算偏移量
            self.limit = self.page_size                     # 一页的数量
        self.has_next = self.page_index < self.page_count   # 是否有下一页，如果当前页数小于了总页数，则没有下一页。
        self.has_previous = self.page_index > 1             # 是否有前一页，如果当前页数小于一，则没有上一页。

    def __str__(self):
        return 'item_count: %s, page_count: %s, page_index: %s, page_size: %s, offset: %s, limit: %s' % (
            self.item_count, self.page_count, self.page_index, self.page_size, self.offset, self.limit)

    __repr__ = __str__

if __name__ == '__main__':
    x = Page(100,11,11)
    import doctest
    doctest.testmod()

