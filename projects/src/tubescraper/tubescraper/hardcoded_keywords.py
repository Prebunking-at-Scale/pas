type OrgName = str
type Keyword = str
type Topics = dict[Keyword, list[str]]


def preprocess_keywords(org_keywords: dict[OrgName, Topics]) -> set[str]:
    res: set[str] = set()
    for _, topic in org_keywords.items():
        for _, keywords in topic.items():
            res.update(keywords)
    return res


org_keywords: dict[OrgName, Topics] = {
    "AAP": {
        "Health": [
            "Corona-Chaos",
            "Impfverweigerer",
            "Corona-Lüge",
            "5G",
            "Übersterblichkeit",
            "Turbokrebs",
            "Plötzlich und unerwartet",
            "Impfopfer",
            "Zwangsimpfung",
            "Impfkomplott",
            "Impfnötigung",
            "Genspritze",
            "Pharmalobby",
            "Impfschäden",
        ],
        "Climate": [
            "Chemtrails",
            "Klima-Wahn",
            "Klima-Hysterie",
            "Klima-Fanatiker",
            "Klimalüge",
            "Klimaschwindler",
            "Klimalobbyismus",
            "Klima-Terror",
            "Geoengineering",
            "Höllensommer",
            "Konsens-Lüge",
        ],
        "EU": [
            "Brüsseler Diktat",
            "Great Reset",
            "Brüsseler Eurokraten",
            "Deep State",
            "Überwachungsstaat",
            "Meinungsdiktatur",
            "Gleichschaltung",
            "Ultraliberalismus",
            "Brüsseler Technokraten",
            "Spitzelstaat",
            "Knüppelstaat",
        ],
        "Migration": [
            "Asylanten",
            "Remigration",
            "Asyl-Chaos",
            "Messermigrantin",
            "Willkommenskultur",
            "Bahnhofsklatscher",
            "Bevölkerungsaustausch",
            "Migrationsversagen",
            "Asyl-Mafia",
            "Ethnische Säuberung",
            "Asyllobby",
            "Moralmission",
        ],
        "Conflict": [
            "Kriegstreiber",
            "Systemmedien",
            "Gender-Wahnsinn",
            "Schlafschafe",
            "Mainstream-Medien",
            "Linksversifft",
            "woke Agenda",
            "Zwangsgebühren",
            "Verlierer-Ampel",
            "Globalisten",
            "Ideologieterror",
        ],
    }
}
