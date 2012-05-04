from graphdatabase import GraphDatabase
from lolreplaysite.constants import DB_LOCATION, HOST, PORT
 
def groupfinder(userid, request):
    # Has 3 potential returns:
    #   - None, meaning userid doesn't exist in our database
    #   - An empty list, meaning existing user but no groups
    #   - Or a list of groups for that userid
    
    gd = GraphDatabase(HOST, PORT, DB_LOCATION)
    g = gd.graph
    user = g.node(type='user', username=userid)
    if user is not None:
        return []
       
