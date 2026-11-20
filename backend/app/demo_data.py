"""A small, hand-written demo dataset.

Every record carries is_demo=True so the UI can clearly label demo results and
never confuse them with a user's uploaded dataset.
"""

from __future__ import annotations

from typing import Any


def demo_records() -> list[dict[str, Any]]:
    rows: list[tuple[str, str, str, str | None, dict[str, Any]]] = [
        ("Product quality is excellent, but delivery was very slow.", "e-commerce", "shopper_01", "2026-11-01T09:12:00Z", {"verified": True, "account_age_days": 820, "followers": 12, "following": 40}),
        ("Absolutely love the build quality. It feels premium and reliable.", "Instagram", "creators_daily", "2026-11-01T10:03:00Z", {"verified": True, "account_age_days": 640, "followers": 12400, "following": 310}),
        ("The packaging was damaged and the item arrived late. Very disappointed.", "Google Reviews", "mrdaniels", "2026-11-01T11:45:00Z", {}),
        ("Customer support responded in minutes and solved my issue. Great service!", "X", "tech_with_sara", "2026-11-01T13:20:00Z", {"verified": False, "account_age_days": 410, "followers": 820, "following": 190}),
        ("Battery life is amazing but the app is confusing to set up.", "Reddit", "pixel_tinker", "2026-11-01T15:02:00Z", {}),
        ("Price feels too high for what you get. I expected better value.", "e-commerce", "reviewer_77", "2026-11-01T17:31:00Z", {}),
        ("Fast shipping, clean packaging, and the product works perfectly. Recommended!", "YouTube", "unboxdaily", "2026-11-01T18:10:00Z", {"verified": True, "account_age_days": 1200, "followers": 45000, "following": 120}),
        ("I am frustrated. The device stopped working after two days.", "Facebook", "angela_m", "2026-11-02T08:05:00Z", {}),
        ("Looks nice in photos but the material feels cheap in person.", "Instagram", "style_room", "2026-11-02T09:40:00Z", {}),
        ("Delivery was quick and the courier was polite. Happy with the purchase.", "Google Reviews", "local_guide", "2026-11-02T10:15:00Z", {}),
        ("The features are useful, especially the scheduling tool. Could be more intuitive though.", "Reddit", "prod_mike", "2026-11-02T12:22:00Z", {}),
        ("Terrible experience. Rude staff and no refund after three weeks.", "X", "consumer_watch", "2026-11-02T14:50:00Z", {"verified": False, "account_age_days": 220, "followers": 3300, "following": 88}),
        ("I was nervous about buying online, but the return policy made it easy. Trustworthy store.", "e-commerce", "cautious_buyer", "2026-11-02T16:30:00Z", {}),
        ("Wow! The new update is genuinely surprising — in a good way.", "YouTube", "gadget_girl", "2026-11-02T18:12:00Z", {}),
        ("Works well. Good quality.", "Google Reviews", "quickreview1", "2026-11-02T19:00:00Z", {"account_age_days": 3, "followers": 2, "following": 900}),
        ("Works well. Good quality.", "Google Reviews", "quickreview1", "2026-11-02T19:01:00Z", {"account_age_days": 3, "followers": 2, "following": 900}),
        ("Works well. Good quality.", "Google Reviews", "quickreview1", "2026-11-02T19:02:00Z", {"account_age_days": 3, "followers": 2, "following": 900}),
        ("BUY NOW limited time discount! Click here for the best price and free shipping.", "Facebook", "promo_deals_daily", "2026-11-02T19:03:00Z", {"account_age_days": 4, "followers": 8, "following": 1500}),
        ("Follow me, link in bio, amazing giveaway today only!!!!", "Instagram", "promo_deals_daily", "2026-11-02T19:04:00Z", {"account_age_days": 4, "followers": 8, "following": 1500}),
        ("The support team was patient and explained every step. I really appreciate it.", "X", "help_seeker", "2026-11-03T07:44:00Z", {}),
        ("Product quality is excellent, but delivery was very slow.", "e-commerce", "shopper_02", "2026-11-03T08:15:00Z", {"account_age_days": 6, "followers": 1, "following": 700}),
        ("Product quality is excellent, but delivery was very slow.", "e-commerce", "shopper_03", "2026-11-03T08:16:00Z", {"account_age_days": 5, "followers": 1, "following": 720}),
        ("I am angry about the hidden fees at checkout. This feels like a scam.", "Reddit", "fedup_user", "2026-11-03T09:30:00Z", {}),
        ("The app is easy to use and the instructions were clear. Setup took five minutes.", "YouTube", "regular_reviewer", "2026-11-03T11:05:00Z", {}),
        ("It broke during the first week. I want a refund or a replacement.", "Google Reviews", "unhappy_customer", "2026-11-03T12:18:00Z", {}),
        ("Genuinely impressed by the reliability. Three months in and zero issues.", "e-commerce", "long_term_user", "2026-11-03T14:40:00Z", {}),
        ("Cheap packaging meant the screen was scratched. Disappointed with the delivery process.", "Facebook", "photo_checker", "2026-11-03T16:20:00Z", {}),
        ("Can someone explain the new settings? I am confused.", "Reddit", "new_to_this", "2026-11-03T17:55:00Z", {}),
        ("Customer service could improve, but the product itself is great.", "Instagram", "balanced_review", "2026-11-04T08:10:00Z", {}),
        ("Best purchase this year! So excited to use it every day.", "X", "happy_buyer", "2026-11-04T09:25:00Z", {}),
        ("Price is fair for the features included. Good value overall.", "e-commerce", "value_checker", "2026-11-04T10:40:00Z", {}),
        ("Delivery tracking never updated and support ignored my messages. Frustrating.", "Google Reviews", "waiting_customer", "2026-11-04T12:05:00Z", {}),
        ("Excellent quality, fast delivery, helpful support. I recommend it.", "YouTube", "review_hub", "2026-11-04T14:30:00Z", {}),
        ("I hope they add dark mode and a better mobile layout in the next update.", "Reddit", "feature_fan", "2026-11-04T16:15:00Z", {}),
        ("Very good. Nice product. Works well. Best ever!", "Facebook", "generic_account_1", "2026-11-04T16:16:00Z", {"account_age_days": 2, "followers": 3, "following": 800}),
        ("Very good. Nice product. Works well. Best ever!", "Facebook", "generic_account_2", "2026-11-04T16:17:00Z", {"account_age_days": 2, "followers": 4, "following": 810}),
        ("The fear of losing my data stopped me from updating, but the migration was safe.", "X", "cautious_tech", "2026-11-04T18:00:00Z", {}),
    ]

    return [
        {
            "id": f"demo-{idx + 1}",
            "text": text,
            "platform": platform,
            "author": author,
            "timestamp": timestamp,
            "metadata": metadata,
            "source_type": "demo",
            "is_demo": True,
        }
        for idx, (text, platform, author, timestamp, metadata) in enumerate(rows)
    ]
