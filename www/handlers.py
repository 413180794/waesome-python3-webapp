'url handlers'
import hashlib
import json
import logging
import re
import time

import markdown2 as markdown2

from aiohttp import web, request

from apis import APIValueError, APIError, APIPermissionError
from config import configs
from coroweb import get, post
from models import User, Blog, next_id, Comment

COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')


def text2html(text):
    # 将text转换为html，替换了& 为 &amp; < 为 &lt; > 为&gt;
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'),
                filter(lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)


def check_admin(request):  # 什么意思？
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()


def get_page_index(page_str):  # 什么意思？
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p


def user2cookie(user, max_age):
    '''利用用户信息生成cookie值 SHA1("用户id"+"用户密码"+"过期时间"+"SecretKey" '''
    expires = str(int(time.time() + max_age))  # 过期时间
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode('utf8')).hexdigest()]
    # L = ["用户id" + "过期时间" + SHA1("用户id" + "用户口令" + "过期时间" + "SecretKey")]
    return '-'.join(L)


async def cookie2user(cookie_str):
    '''解析cookie 如果cookie合法，载入用户，'''
    if not cookie_str:  # 如果cookie是空的，返回空
        return None
    try:  # 捕获哪一步错误？
        L = cookie_str.split('-')  # 拆成 用户id 过期时间 SHA1("用户id" + "用户口令" + "过期时间" + "SecretKey")
        if len(L) != 3:  # 如果cookie的规则不符合要求，直接返回None
            return None
        uid, expires, sha1 = L  # 用户id，过期时间，sha1
        if int(expires) < time.time():  # 如果过期时间超过当前时间
            return None
        user = await User.find(uid)  # 通过uid找对应的用户
        if user is None:
            return None  # 如果没有找到，返回空
        s = "%s-%s-%s-%s" % (uid, user.passwd, expires, _COOKIE_KEY)  # 在计算一次sha1，确保两次sha1相同
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info("invalid sha1")
            return None
        user.passwd = "******"  # 这句是在做什么？
        return user
    except  Exception as e:
        logging.exception(e)
        return None


@get("/register")
def register():
    # 进入注册界面
    return {
        "__template__": "register.html"
    }


@get("/signin")
def signin():
    # 进入登录界面
    return {
        "__template__": "signin.html"
    }


@get("/manage/blogs")
def manage_blogs(*, page="1"):
    return {
        "__template__": "manage_blogs.html",
        "page_index": get_page_index(page)
    }


@get("/manage/blogs/create")
def manage_create_blog():
    # 管理创建博客
    return {
        "__template__": "manage_blog_edit.html",
        "id": "",
        "action": "/api/blogs"
    }


@get('/blog/{id}')
async def get_blog(id):
    blog = await Blog.find(id)
    if not blog:  # 并没有这篇博客
        raise APIValueError("没有这篇博客")
    print(blog)
    comments = await Comment.findAll("blog_id=?", [id], orderBy="created_at desc")
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = markdown2.markdown(blog.content)
    return {
        "__template__": "blog.html",
        "blog": blog,
        "comments": comments
    }


@post("/api/authenticate")
async def authenticate(*, email, passwd):
    # 校验用户信息
    if not email:
        raise APIValueError("email", "Invalid email.")
    if not passwd:
        raise APIValueError("passwd", "Invalid password.")
    users = await User.findAll("email=?", [email])
    if len(users) == 0:
        raise APIValueError("email", "Email not exist.")
    user = users[0]
    sha1 = hashlib.sha1()  # 校验密码的方式是 sha1("用户名:密码")
    sha1.update(user.id.encode("utf8"))
    sha1.update(b":")
    sha1.update(passwd.encode("utf8"))
    if user.passwd != sha1.hexdigest():  # 如果密码不同，返回错误
        raise APIValueError("passwd", "Invalid password")  # 为什么这里抛出异常会导致对应的界面显示出Invalid password
    # 如果密码正确，设置cookie
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = "******"
    r.content_type = "application/json"
    r.body = json.dumps(user, ensure_ascii=False).encode('utf8')
    return r


@get("/signout")
def signout(request):
    referer = request.headers.get("Referer")
    r = web.HTTPFound(referer or "/")
    r.set_cookie(COOKIE_NAME, "-deleted-", max_age=0, httponly=True)
    logging.info("user signed out.")
    return r


@post("/api/users")
async def api_register_user(*, email, name, passwd):
    if not name or not name.strip():  # 检查名字是否为空
        raise APIValueError("name")
    if not email or not _RE_EMAIL.match(email):  # 检查邮箱是否为空，是否符合规范
        raise APIValueError("email")
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError("passwd")
    users = await User.findAll("email=?", [email])
    if len(users) > 0:  # 检测该email是否被使用过
        raise APIError("register:failed", "email", "Email is already in use.")
    uid = next_id()  # 生成一个随机数作为主键
    sha1_passwd = "%s:%s" % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),
                image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    # 设置cookie

    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = "******"
    r.content_type = "application/json"
    r.body = json.dumps(user, ensure_ascii=False).encode('utf8')
    return r


@get("/api/blogs/{id}")
async def api_get_blog(*, id):
    # 获取博客的api
    blog = await Blog.find(id)
    return blog


@post("/api/blogs")
async def api_create_blog(request, *, name, summary, content):
    # 创建博客的api
    # 问题：如何理解这个request的作用
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError("name", "name cannot be empty.")
    if not summary or not summary.strip():
        raise APIValueError("summary", "summary cannot be empty.")
    if not content or not content.strip():
        raise APIValueError("content", "content cannot be empty.")
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image,
                name=name.strip(), summary=summary.strip(), content=content.strip())
    await blog.save()
    return blog


@get("/")
async def index():
    summary = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
    blogs = [
        Blog(id='1', name='Test Blog', summary=summary, created_at=time.time() - 120),
        Blog(id='2', name='Something New', summary=summary, created_at=time.time() - 3600),
        Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time() - 7200)
    ]
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }


@get('/api/users')
def api_get_users():
    users = yield from User.findAll(orderBy='created_at desc')
    for u in users:
        u.passwd = '******'
    return dict(users=users)
