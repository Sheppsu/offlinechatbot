"""
Meant to be moved to the main directory when running
"""
import sys

if len(sys.argv) < 2:
    print("Must provide an a user and how much money to give them.")
    quit()

if not sys.argv[2].isnumeric():
    print("Money must be a valid number.")
    quit()

user = sys.argv[1]
money = float(sys.argv[2])

from dotenv import load_dotenv
load_dotenv()

from sql import Database


db = Database()
userdata = db.get_userdata()

if user not in userdata:
    print("You did not supply a valid user")
    quit()

db.update_userdata(user, "money", userdata[user]["money"]+money)
