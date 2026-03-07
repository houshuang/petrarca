Open in app

Sign up

Sign in

Write

Member-only story

# Why SQLite Is the Database You Didn't Know You Needed

## A deep dive into the world's most deployed database engine

[![Alex Rivera](https://miro.medium.com/v2/resize:fill:88:88/avatar.jpg)](https://medium.com/@alexrivera)

[Alex Rivera](https://medium.com/@alexrivera) · Follow

Published in Towards Data Science · 12 min read · Feb 28, 2026

--

Listen

Share

More

![Header image showing a database icon](https://miro.medium.com/v2/resize:fit:700/1*abc123.jpeg)

Photo by [Unsplash](https://unsplash.com) on [Unsplash](https://unsplash.com)

SQLite is everywhere. It's in your phone, your browser, your car, and probably your refrigerator. With over one trillion active databases worldwide, it's the most widely deployed database engine in history.

Yet many developers dismiss it as a "toy database." They're wrong, and here's why.

## The Architecture

SQLite is a serverless, self-contained, zero-configuration database engine. Unlike PostgreSQL or MySQL, it doesn't run as a separate process — it's a library that gets linked directly into your application.

```sql
-- That's it. This creates a full ACID-compliant database.
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE
);
```

The entire database is stored in a single cross-platform file. You can copy it, email it, put it in Git — it's just a file.

## Why SQLite Wins for Most Applications

Here's the uncomfortable truth: **most applications don't need a client-server database**.

If your application:
- Has fewer than 100,000 write transactions per day
- Runs on a single machine
- Doesn't need concurrent write access from multiple processes

Then SQLite is probably the better choice. And the benefits are enormous:

1. **Zero administration** — no server to configure, monitor, or upgrade
2. **Atomic transactions** — full ACID compliance with WAL mode
3. **Cross-platform** — the file format is stable and platform-independent
4. **Incredibly fast** — for read-heavy workloads, it's often faster than PostgreSQL

## The WAL Revolution

Write-Ahead Logging (WAL) mode changed everything. Before WAL, SQLite used a rollback journal that blocked readers during writes. WAL allows concurrent reads during a write transaction:

```sql
PRAGMA journal_mode=WAL;
```

With WAL, SQLite can handle thousands of concurrent readers while a single writer is active. For most web applications, this is more than sufficient.

## Real-World Usage

Companies using SQLite in production:
- **Apple** — every iPhone runs dozens of SQLite databases
- **Google** — Chrome, Android, and many internal tools
- **Airbus** — flight management systems
- **Bloomberg** — financial data analysis tools

## The Edge Computing Connection

The rise of edge computing has made SQLite even more relevant. When you're running at the edge — on IoT devices, in serverless functions, or on mobile — you need a database that:

- Starts instantly
- Uses minimal memory
- Doesn't require network access
- Is extremely reliable

SQLite checks every box.

## Conclusion

The next time you reach for PostgreSQL or MySQL, ask yourself: do I actually need a client-server database? Chances are, SQLite will serve you better.

---

Thanks for reading! If you found this helpful, please consider:

👏 Clapping up to 50 times

💬 Leaving a comment below

🔔 Following me for more database deep dives

---

[Alex Rivera](https://medium.com/@alexrivera) · Follow

Written by Alex Rivera

1.2K Followers · Writer for Towards Data Science

More from Alex Rivera

More from Towards Data Science

Recommended from Medium

[See all from Alex Rivera](https://medium.com/@alexrivera)

[See all from Towards Data Science](https://towardsdatascience.com)

[![](https://miro.medium.com/v2/resize:fill:140)](https://medium.com/@someone/related-post)

### Related Post Title Here

Some description of a related post that Medium recommends...

---

[About](https://medium.com/about) [Help](https://help.medium.com) [Terms](https://policy.medium.com/medium-terms-of-service-9db0094a1e0f) [Privacy](https://policy.medium.com/medium-privacy-policy-f03bf92035c9)

---

Get the Medium app

[![A button that says 'Download on the App Store'](https://miro.medium.com/v2/appstore.png)](https://itunes.apple.com/app)
[![A button that says 'Get it on, Google Play'](https://miro.medium.com/v2/googleplay.png)](https://play.google.com/store/apps)

[Status](https://medium.statuspage.io) [Blog](https://blog.medium.com) [Careers](https://medium.com/jobs-at-medium)

Text to speech
