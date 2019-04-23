# 这个配置文件简单明了。但是，如果要部署到服务器时，通常需要修改数据库的host等信息，直接修改这个文件不是一个好办法，
# 更好点的办法是编写一个config_override.py，用来覆盖某些默认设置

configs = {
    'debug': True,
    "db": {
        "host": "localhost",
        "port": 3306,
        "user": "root",
        "password": "admin",
        'db': "awesome"
    },
    "session": {
        "secret":"AwEsOmE",
    }
}
