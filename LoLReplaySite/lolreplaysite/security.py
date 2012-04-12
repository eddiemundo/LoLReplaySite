from GraphDatabase import GraphDatabase

# copied from view.py... i smell refactoring 
db_location = 'lolreplaysite/databases/lolreplaysite.gd'

def groupfinder(userid, request):
    # Has 3 potential returns:
    #   - None, meaning userid doesn't exist in our database
    #   - An empty list, meaning existing user but no groups
    #   - Or a list of groups for that userid
    
    gd = GraphDatabase(db_location)
    users = gd.graph.findNodesByProperty('type', 'user')
    user = gd.graph.findNodesByProperty('username', userid)
    if user:
        return []