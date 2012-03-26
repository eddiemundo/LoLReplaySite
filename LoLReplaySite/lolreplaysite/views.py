from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound
from pyramid.renderers import get_renderer

def site_layout():
	renderer = get_renderer("templates/main.pt")
	layout = renderer.implementation().macros['layout']
	return layout

@view_config(route_name='home', renderer='templates/main.pt')
def home(request):
    return {'layout': site_layout(), 'replay_list': []}

@view_config(route_name='replays', renderer='templates/replays.pt')
def replays(request):
 	return {'layout': site_layout(), 'replay_list': []}
