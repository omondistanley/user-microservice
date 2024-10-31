# User Microservice for the expense tracker

Implemented the Crud operations for the user, mainly getting a specific user by email, getting all users(not fully implemented - having a bug with the pagination), and post for registering new users. 
Implemented Pagination only for cases when we're to get all the users... a page has a limit of ten entries
Implemented HATEOAS, using the userID.

#Output for get user by email:
![Alt text](get1.png)
![Alt text](get2.png)
#Output for posting a new user:
![Alt text](post1.png)
![Alt text](post2.png)
#Output for getting all the registered users.
[bug from pagination solved, inconsistency between related functions: get_all and get_data_objects_(which get_all calls and is responsible for geting every user from the database)_]
![Alt text](getall1.png)
![Alt text](getall2.png)
![Alt text](getall3.png)
