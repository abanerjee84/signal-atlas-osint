# Public RSS and Atom directory

Discovery references: [awesome-osint](https://github.com/jivoi/awesome-osint) and [awesome-rss-feeds](https://github.com/plenaryapp/awesome-rss-feeds). Sources are individually selected and bounded; list membership does not guarantee access, factual reliability or redistribution rights.

This directory records configured public RSS/Atom sources. Eighteen additional conflict and defence feeds are listed in the [conflict source audit](CONFLICT_SOURCE_AUDIT.md#verified-additional-feeds) and implemented in `backend/connectors/conflict_sources.py`. Mixed conflict feeds route military wording to Military OSINT and political/security reporting to Geopolitics. This directory describes configuration, not live health. Visit the in-app source status for current failures. Feed excerpts retain attribution and original links.

| Source                                                         | Layer        | Refresh (minutes) | Feed                                                                                           |
| -------------------------------------------------------------- | ------------ | ----------------- | ---------------------------------------------------------------------------------------------- |
| BBC world headlines                                            | geopolitical | 30                | [RSS/Atom](https://feeds.bbci.co.uk/news/world/rss.xml)                                        |
| NATO public announcements                                      | military     | 30                | [RSS/Atom](https://www.nato.int/cps/en/natohq/news.rss)                                        |
| ECB releases and statements                                    | economic     | 30                | [RSS/Atom](https://www.ecb.europa.eu/rss/press.html)                                           |
| UK Ministry of Defence announcements                           | military     | 30                | [RSS/Atom](https://www.gov.uk/government/organisations/ministry-of-defence.atom)               |
| SANS Internet Storm Center diary                               | cyber        | 60                | [RSS/Atom](https://isc.sans.edu/rssfeed_full.xml)                                              |
| Citizen Lab investigations and updates                         | cyber        | 60                | [RSS/Atom](https://citizenlab.ca/feed/)                                                        |
| Krebs on Security investigations                               | cyber        | 60                | [RSS/Atom](https://krebsonsecurity.com/feed/)                                                  |
| defend.network automated briefings                             | cyber        | 60                | [RSS/Atom](https://defend.network/feed.xml)                                                    |
| Cisco Talos research attack reports                            | threat       | 15                | [RSS/Atom](https://blog.talosintelligence.com/rss/)                                            |
| BleepingComputer attack reports                                | threat       | 15                | [RSS/Atom](https://www.bleepingcomputer.com/feed/)                                             |
| SecurityWeek attack reports                                    | threat       | 15                | [RSS/Atom](https://www.securityweek.com/feed/)                                                 |
| The Hacker News attack reports                                 | threat       | 15                | [RSS/Atom](https://feeds.feedburner.com/TheHackersNews)                                        |
| The Record attack reports                                      | threat       | 15                | [RSS/Atom](https://therecord.media/feed)                                                       |
| Cybersecurity Dive attack reports                              | threat       | 15                | [RSS/Atom](https://www.cybersecuritydive.com/feeds/news/)                                      |
| ESET WeLiveSecurity attack reports                             | threat       | 15                | [RSS/Atom](https://www.welivesecurity.com/en/rss/feed/)                                        |
| Microsoft Security research attack reports                     | threat       | 15                | [RSS/Atom](https://www.microsoft.com/en-us/security/blog/feed/)                                |
| Guardian Middle East                                           | geopolitical | 30                | [RSS/Atom](https://www.theguardian.com/world/middleeast/rss)                                   |
| Guardian Europe                                                | geopolitical | 30                | [RSS/Atom](https://www.theguardian.com/world/europe-news/rss)                                  |
| Guardian South Asia                                            | geopolitical | 30                | [RSS/Atom](https://www.theguardian.com/world/south-and-central-asia/rss)                       |
| Guardian Australia                                             | geopolitical | 30                | [RSS/Atom](https://www.theguardian.com/australia-news/rss)                                     |
| Al-Monitor Middle East                                         | geopolitical | 30                | [RSS/Atom](https://www.al-monitor.com/rss)                                                     |
| International Crisis Group analysis                            | geopolitical | 30                | [RSS/Atom](https://www.crisisgroup.org/rss.xml)                                                |
| SCMP world reporting                                           | geopolitical | 30                | [RSS/Atom](https://www.scmp.com/rss/91/feed/)                                                  |
| NPR world                                                      | geopolitical | 30                | [RSS/Atom](https://feeds.npr.org/1004/rss.xml)                                                 |
| Mastodon #geopolitics                                          | sentiment    | 15                | [RSS/Atom](https://mastodon.social/tags/geopolitics.rss)                                       |
| Mastodon #ukraine                                              | sentiment    | 15                | [RSS/Atom](https://mastodon.social/tags/ukraine.rss)                                           |
| Mastodon #cybersecurity                                        | sentiment    | 15                | [RSS/Atom](https://mastodon.social/tags/cybersecurity.rss)                                     |
| Lemmy World c/world                                            | sentiment    | 15                | [RSS/Atom](https://lemmy.world/feeds/c/world.xml?sort=New)                                     |
| Lemmy World c/technology                                       | sentiment    | 15                | [RSS/Atom](https://lemmy.world/feeds/c/technology.xml?sort=New)                                |
| BBC business and global economy                                | economic     | 30                | [RSS/Atom](https://feeds.bbci.co.uk/news/business/rss.xml)                                     |
| Guardian business and economy                                  | economic     | 30                | [RSS/Atom](https://www.theguardian.com/uk/business/rss)                                        |
| Guardian energy industry                                       | economic     | 30                | [RSS/Atom](https://www.theguardian.com/business/energy-industry/rss)                           |
| CNA international business                                     | economic     | 30                | [RSS/Atom](https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936) |
| US EIA Today in Energy                                         | economic     | 30                | [RSS/Atom](https://www.eia.gov/rss/todayinenergy.xml)                                          |
| DVIDS military public reporting                                | military     | 30                | [RSS/Atom](https://www.dvidshub.net/rss/news)                                                  |
| BBC africa headlines                                           | geopolitical | 30                | [RSS/Atom](https://feeds.bbci.co.uk/news/world/africa/rss.xml)                                 |
| BBC asia headlines                                             | geopolitical | 30                | [RSS/Atom](https://feeds.bbci.co.uk/news/world/asia/rss.xml)                                   |
| BBC europe headlines                                           | geopolitical | 30                | [RSS/Atom](https://feeds.bbci.co.uk/news/world/europe/rss.xml)                                 |
| BBC latin america headlines                                    | geopolitical | 30                | [RSS/Atom](https://feeds.bbci.co.uk/news/world/latin_america/rss.xml)                          |
| BBC middle east headlines                                      | geopolitical | 30                | [RSS/Atom](https://feeds.bbci.co.uk/news/world/middle_east/rss.xml)                            |
| BBC us and canada headlines                                    | geopolitical | 30                | [RSS/Atom](https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml)                          |
| Al Jazeera headlines                                           | geopolitical | 30                | [RSS/Atom](https://www.aljazeera.com/xml/rss/all.xml)                                          |
| DW international headlines                                     | geopolitical | 30                | [RSS/Atom](https://rss.dw.com/rdf/rss-en-all)                                                  |
| Guardian world headlines                                       | geopolitical | 30                | [RSS/Atom](https://www.theguardian.com/world/rss)                                              |
| France 24 English headlines                                    | geopolitical | 30                | [RSS/Atom](https://www.france24.com/en/rss)                                                    |
| UN News — global diplomacy and humanitarian reporting          | geopolitical | 30                | [RSS/Atom](https://news.un.org/feed/subscribe/en/news/all/rss.xml)                             |
| Africanews — Africa headlines                                  | geopolitical | 30                | [RSS/Atom](https://www.africanews.com/feed/rss)                                                |
| MercoPress — South Atlantic and Latin America                  | geopolitical | 30                | [RSS/Atom](https://en.mercopress.com/rss)                                                      |
| Buenos Aires Herald — Argentina and regional affairs           | geopolitical | 30                | [RSS/Atom](https://buenosairesherald.com/feed)                                                 |
| CNA — world headlines                                          | geopolitical | 30                | [RSS/Atom](https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6311) |
| CNA — Asia headlines                                           | geopolitical | 30                | [RSS/Atom](https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6511) |
| RFI — international headlines                                  | geopolitical | 30                | [RSS/Atom](https://www.rfi.fr/en/rss)                                                          |
| ABC Australia — selected international and political headlines | geopolitical | 30                | [RSS/Atom](https://www.abc.net.au/news/feed/51120/rss.xml)                                     |
| Euronews — international reporting                             | geopolitical | 30                | [RSS/Atom](https://www.euronews.com/rss?level=theme&name=news)                                 |
| Guardian — Africa headlines                                    | geopolitical | 30                | [RSS/Atom](https://www.theguardian.com/world/africa/rss)                                       |
| Guardian — Americas headlines                                  | geopolitical | 30                | [RSS/Atom](https://www.theguardian.com/world/americas/rss)                                     |
| Guardian — Asia headlines                                      | geopolitical | 30                | [RSS/Atom](https://www.theguardian.com/world/asia/rss)                                         |
| Reddit r/worldnews new                                         | sentiment    | 30                | [RSS/Atom](https://www.reddit.com/r/worldnews/new/.rss?limit=100)                              |
| Reddit r/worldnews comments                                    | sentiment    | 30                | [RSS/Atom](https://www.reddit.com/r/worldnews/comments/.rss?limit=100)                         |
| Reddit r/geopolitics new                                       | sentiment    | 30                | [RSS/Atom](https://www.reddit.com/r/geopolitics/new/.rss?limit=100)                            |
| Reddit r/geopolitics comments                                  | sentiment    | 30                | [RSS/Atom](https://www.reddit.com/r/geopolitics/comments/.rss?limit=100)                       |
| Reddit r/climate new                                           | sentiment    | 30                | [RSS/Atom](https://www.reddit.com/r/climate/new/.rss?limit=100)                                |
| Reddit r/climate comments                                      | sentiment    | 30                | [RSS/Atom](https://www.reddit.com/r/climate/comments/.rss?limit=100)                           |
| BBC News uploads                                               | geopolitical | 30                | [RSS/Atom](https://www.youtube.com/feeds/videos.xml?channel_id=UC16niRr50-MSBwiO3YDb3RA)       |
| DW News uploads                                                | geopolitical | 30                | [RSS/Atom](https://www.youtube.com/feeds/videos.xml?channel_id=UCknLrEdhRCp1aegoMqRaCZg)       |
| Al Jazeera English uploads                                     | geopolitical | 30                | [RSS/Atom](https://www.youtube.com/feeds/videos.xml?channel_id=UCNye-wNBqNL5ZzHSJj3l8Bg)       |

Public Telegram channel previews use HTML instead of RSS. Configure permitted channels with `OSINT_TELEGRAM_CHANNELS`; robots restrictions and missing/private previews fail visibly. A missing robots file permits public preview collection. Existing Reddit archive adapters and manual browser imports are separately labelled deliveries and are not RSS.
