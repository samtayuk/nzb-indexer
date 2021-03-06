# index.py
# Scott Metoyer, 2013
# Retrieves a list of new NZB's from the newsgroups specified in a config file
from nntplib import *
from pymongo import MongoClient
import string
import datetime
import time

try:
    from config_local import config as config
except ImportError:
     from config_default import config as config

mongo_connection = MongoClient('localhost', 27017)
db = mongo_connection.nzb_database
newsgroups = db.newsgroup_collection
articles = db.article_collection

def connect():
    print('Connecting to ' + config["usenet_server"] + '...')
    server = NNTP(config["usenet_server"], config["usenet_port"], config["usenet_username"], config["usenet_password"])
    return server
    
def fetch_articles(group, start_index):
    article_count = 0    
    server = connect()
    
    print('Reading from group ' + group + '...')
    resp, count, first, last, name = server.group(group)
  
    print('Getting a list of nzb files in ' + group + '...')

    if start_index < int(first):
        start_index = int(first)
        
    current_index = int(start_index)
    last_index = int(last)
    chunk_size = 10000

    # Some sanity checking on the maximum number to process. If it's too many, we only grab the newest.
    if last_index - current_index > config["max_run_size"]:
        current_index = last_index - config["max_run_size"]
    
    while (current_index < last_index):
        if (current_index + chunk_size >= last_index):
            chunk_size = last_index - current_index
        
        try:
            resp, items = server.xover(str(current_index), str(current_index + chunk_size))
        except:
            print("Error grabbing articles. Attempting to reconnect...")
            server = connect()
            server.group(group)
            resp, items = server.xover(str(current_index), str(current_index + chunk_size))
            print("Reconnected.")
            
        for number, subject, poster, date, id, references, size, lines in items:
            if '.nzb' in subject.lower():
                # Check make sure this article doesn't exist in the database already
                if articles.find_one({"message-id": id}) == None:
                    article = {"message-id": id,
                               "group": group,
                               "article-number": number,
                               "subject": subject,
                               "date": date}
                    try:
                        articles.insert(article)
                        print(group + "," + number + ": " + subject)
                        article_count += 1
                    except:
                        print("Error inserting article. Continuing...")
                else:
                    print("Article " + id + " already exists in the database. Continuing...")
                
        current_index += chunk_size
        
    server.quit()
    print("Articles added: " + str(article_count))
    return current_index
    
def get_group(group_name):
    group = newsgroups.find_one({"name": group_name})
    
    if group == None:
        group = {"name": group_name,
                 "last_scan": datetime.datetime.now(),
                 "last_article": 0}
        newsgroups.insert(group)
        
    return group

def update_group(group_name, last_article):
    # Make sure the group exists
    get_group(group_name)
    
    newsgroups.update({"name": group_name}, 
                      {"$set":  {
                                    "last_scan": datetime.datetime.now(), 
                                    "last_article": last_article
                                }
                      })
    
# Grab groups to scan from configuration file
f = open("groups.txt", "r")
groups = (line.strip() for line in f.readlines() if len(line.strip()))
f.close()

print("Starting run...")
start = time.time()

for group_name in groups:
    group_name = group_name
    settings = get_group(group_name)
    last_index = fetch_articles(group_name, settings["last_article"] + 1)
    update_group(group_name,  last_index)
    
end = time.time()
elapsed = end - start
print("Execution time: " + str(elapsed / 60) + " minutes")