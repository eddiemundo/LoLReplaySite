from pyramid.config import Configurator

def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    config = Configurator(settings=settings)
    config.add_static_view('static', 'static', cache_max_age=3600)
    config.add_route('home', '/')
    config.add_route('replays', '/replays')
    config.add_route('news', '/news')
    config.add_route('upload_a_replay', '/upload_a_replay')
    config.add_route('upload_replay', '/upload_replay')
    config.add_route('download_replay', '/download/replay/{id}.{ext}')
    config.scan()
    return config.make_wsgi_app()
