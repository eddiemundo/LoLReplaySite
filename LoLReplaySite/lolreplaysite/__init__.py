from pyramid.config import Configurator
from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.session import UnencryptedCookieSessionFactoryConfig
my_session_factory = UnencryptedCookieSessionFactoryConfig('sekrit2')


from lolreplaysite.security import groupfinder



def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    config = Configurator(
						settings=settings,
						authentication_policy=AuthTktAuthenticationPolicy(
																		secret='sekrit',
																		callback=groupfinder,
																		timeout=1200,
																		reissue_time=120),
						session_factory = my_session_factory,
						)
    config.add_static_view('static', 'static', cache_max_age=3600)
    config.add_route('home', '/')
    config.add_route('replays', '/replays')
    config.add_route('faq', '/faq')
    config.add_route('feedback', '/feedback')
    
    config.add_route('personal_view', '/personal')
    
    config.add_route('upload', '/upload')
    config.add_route('upload_replay', '/upload_replay')
    config.add_route('download_replay', '/download/replay/{id}.{ext}')
    config.add_route('login', '/login')
    config.add_route('logout', '/logout')
    config.add_route('register', '/register')
    config.scan()
    return config.make_wsgi_app()
