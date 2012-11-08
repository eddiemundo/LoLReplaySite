LoLReplaySite README

The purpose of this web app is to be able to share and review League of Legends replays (lolreplay files). The official lolreplay site has a little of this ability already, but this site is just for my friends and "clanmates", and has a focus on "reviews".

Some features:
- User accounts
- Ability to upload replays
- General comments on replays
- Replay downloads
- Private comments on replays
- Ability to invite specific users to review your replay
- Notifications of comments, replies, replays invited to review, reviews on your replays
- and more...

Current status:
This build is a proof of concept. It works, and has most of the above features except certain notifications, and any email notifications. Probably 70-80% feature complete, but most of basic functionality is done.

Technology:
Written in python using the Pyramid framework. Anything that doesn't come with the framework was written from scratch. The database used is my "eddb" project which is also found on my github. I don't suggest anyone use it. It's basically a graph database with the bare minimum features, and does not use a server/client architecture. Also has security holes, and is not scalable. Also was gonna do an api redesign on it...