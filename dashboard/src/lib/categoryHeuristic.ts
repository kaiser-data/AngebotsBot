/**
 * Title-first classification into the canonical (bucket, subcategory) pairs
 * from taxonomy.json / taxonomy.ts.
 *
 * Signal priority:
 *   1. Hard brand rules (Ariel→Waschmittel, Apple iPhone→Smartphone, etc).
 *      These are exact phrases that DEFINITIVELY resolve a product, regardless
 *      of what the noisy kaufDA category column says.
 *   2. Title-keyword rules. The title carries product info — "Ariel Universal
 *      Waschpulver 80WL" tells us exactly what it is even when kaufda_category
 *      is just "Ariel".
 *   3. Category-keyword rules (legacy). Used only when title yields no match.
 */

import { BUCKETS, type Bucket } from "./taxonomy";

export { BUCKETS };
export type { Bucket };

export type Classification = { bucket: Bucket; subcategory: string };

// ── 1. Hard brand/keyword rules — checked against title FIRST ────────────────
// Each entry is [bucket, subcategory, RegExp-anchored phrase]. Order matters
// only when phrases overlap; first match wins.
const HARD_RULES: ReadonlyArray<readonly [Bucket, string, RegExp]> = [
  // Apple-the-brand → Elektronik (resolves the "Apfel" collision)
  ["Elektronik & Multimedia", "Smartphone & Tablet", /\b(?:iphone|ipad|airpods?)\b/i],
  ["Elektronik & Multimedia", "Computer & Drucker", /\b(?:macbook|imac|mac mini)\b/i],
  ["Elektronik & Multimedia", "TV & Audio", /\bapple tv\b/i],

  // Detergent / cleaning brands → Haushalt & Reinigung
  ["Haushalt & Reinigung", "Waschmittel",
   /\b(?:ariel|persil|lenor|coral|perwoll|spee|weißer riese|dash)\b/i],
  ["Haushalt & Reinigung", "Reinigung",
   /\b(?:frosch|ajax|febreze|ecover|sagrotan|domestos|finish|somat)\b/i],

  // Cat food brands
  // "Gourmet" alone is too generic ("Gourmet Burger") — only its cat-food lines.
  ["Tier", "Katze",
   /\b(?:felix|whiskas|sheba|kitekat|catsan|gourmet[\s-]+(?:gold|perle|a la carte|mon petit|revolution))\b/i],
  // Dog food brands
  ["Tier", "Hund", /\b(?:pedigree|frolic|chappi|cesar|rinti)\b/i],

  // Baby brands
  ["Baby & Kind", "Windeln & Pflege", /\b(?:pampers|huggies|babylove|lillydoo)\b/i],
  ["Baby & Kind", "Baby-Nahrung", /\b(?:hipp|alete|milupa|aptamil)\b/i],

  // Snack/chip/sweets brands
  ["Lebensmittel", "Süßwaren & Snacks",
   /\b(?:funny[\s-]*frisch|chio|lay'?s|pringles|ferrero|milka|ritter[\s-]*sport|haribo|amicelli|m&m'?s)\b/i],
  // Ferrero's "Kinder" line only — not "Kinder-Fahrrad" or "Kinderschuhe".
  ["Lebensmittel", "Süßwaren & Snacks",
   /\bkinder[\s-]+(?:schokolade|riegel|bueno|country|pingui|maxi|überraschung|happy hippo|joy|delice|milchschnitte|cards|choco)/i],

  // Alcohol brands → Getränke
  ["Getränke", "Spirituosen",
   /\b(?:aperol|campari|cinzano|martini|jägermeister|absolut|smirnoff|bombay|tanqueray|nordhäuser)\b/i],
  ["Getränke", "Bier",
   /\b(?:beck'?s|krombacher|warsteiner|bitburger|veltins|flensburger|feldschlößchen|paulaner)\b/i],
  ["Getränke", "Wasser & Säfte",
   /\b(?:coca[\s-]*cola|pepsi|fanta|sprite|fritz[\s-]*kola|afri[\s-]*cola|red bull|gerolsteiner|vio|volvic)\b/i],
];

// ── 2. Title-keyword rules — checked second ──────────────────────────────────
// More general substrings. Run AFTER hard rules so brand collisions resolve first.
// Order: niche/specific buckets first, broad food/drink last.
type Rule = readonly [Bucket, string, readonly string[]];

const TITLE_RULES: readonly Rule[] = [
  // Baby & Kind
  ["Baby & Kind", "Windeln & Pflege",
    ["windel", "feuchttuch", "babylotion", "babybad", "babyshampoo", "babypfleg"]],
  ["Baby & Kind", "Baby-Nahrung",
    ["babynahrung", "babybrei", "folgemilch", "anfangsmilch", "babykost", "babyglas"]],
  ["Baby & Kind", "Spielzeug",
    ["spielzeug", "lego", "playmobil", "puppe", "kuscheltier", "stofftier",
     "kinderwagen", "kinderbett", "maxi-cosi", "schulranzen", "schultasche"]],

  // Tier
  ["Tier", "Hund",
    ["hundefutter", "hundeleckerli", "hundeleine", "hundehalsband", "hundekauknochen"]],
  ["Tier", "Katze",
    ["katzenfutter", "katzenstreu", "katzenleckerli"]],
  ["Tier", "Sonstige Tiere",
    ["nagerfutter", "vogelfutter", "aquarium", "terrarium", "fischfutter",
     "kaninchen", "meerschweinchen", "ziervogel"]],

  // Garten & Heimwerken — tools first (more specific)
  ["Garten & Heimwerken", "Gartenwerkzeug",
    ["rasenmäher", "rasenmaeher", "heckenschere", "akku-heckenschere", "akku-rasenmäher",
     "akku-rasenmaeher", "kettensäge", "kettensaege", "akku-kettensäge", "astschere",
     "gartenschere", "laubbläser", "vertikutierer", "akku-bohrschrauber", "gartenschlauch"]],
  ["Garten & Heimwerken", "Pflanzen & Garten",
    ["pflanze", "blume ", "azalee", "samen", "dünger", "duenger", "rasensaat", "blumenkasten", "blumenerde", "pflanzerde", "orchidee"]],
  ["Garten & Heimwerken", "Gartenmöbel",
    ["ampelschirm", "faltpavillon", "feuerschale", "gartenstuhl", "gartentisch",
     "auflagenbox", "abdeckhaube", "anzündkamin", "anzuendkamin", "briketts", "grill", "holzkohle"]],
  ["Garten & Heimwerken", "Farbe & Bauchemie",
    ["wandfarbe", "lack", "alpina", "farbroller", "silikon", "klebstoff", "fliese"]],
  ["Garten & Heimwerken", "Werkzeug & Heimwerken",
    ["werkzeug", "bohrmaschine", "akkuschrauber", "säge ", "saege ", "hammer", "schraube",
     "dübel", "duebel", "leiter ", "kabeltrommel", "verlängerung", "verlaengerung"]],

  // Elektronik
  ["Elektronik & Multimedia", "Smartphone & Tablet",
    ["smartphone", "handy ", "tablet", "samsung galaxy", "huawei", "xiaomi"]],
  ["Elektronik & Multimedia", "Computer & Drucker",
    ["laptop", "notebook", "drucker", "epson", "tintenpatron", "toner", "monitor",
     "tastatur", "router", "wlan", "festplatte", "ssd ", "usb-stick"]],
  ["Elektronik & Multimedia", "TV & Audio",
    ["fernseher", "fernsehgerät", "soundbar", "lautsprecher", "kopfhörer", "kopfhoerer",
     "bluetooth-box", "blu-ray", "dvd-player", "radio "]],
  ["Elektronik & Multimedia", "Haushaltsgeräte",
    ["staubsauger", "saugroboter", "waschmaschine", "trockner", "geschirrspüler",
     "geschirrspueler", "fritteuse", "mixer", "toaster", "wasserkocher", "kaffeevollautomat",
     "siebträger", "siebtraeger", "mikrowelle", "backofen", "kühlschrank", "kuehlschrank",
     "gefrierschrank", "klimaanlage", "airfryer", "heißluftfritteuse"]],
  ["Elektronik & Multimedia", "Sonstige Elektronik",
    ["ladegerät", "ladegeraet", "powerbank", "akku ", "fernglas", "dartscheibe"]],

  // Mode, Sport & Freizeit
  ["Mode, Sport & Freizeit", "Sport & Fitness",
    ["fitness", "yoga", "hantel", "yogamatte", "fussball", "fußball", "tennis", "basketball",
     "trikot", "sportflasche"]],
  ["Mode, Sport & Freizeit", "Outdoor",
    ["outdoor", "wanderschuh", "rucksack", "zelt", "schlafsack", "camping"]],
  ["Mode, Sport & Freizeit", "Spielzeug & Hobby",
    ["fahrrad", "e-bike", "elektrofahrrad", "e-scooter", "scooter", "rollschuh", "skate"]],
  ["Mode, Sport & Freizeit", "Kleidung & Schuhe",
    ["kleid ", "hose ", "jacke", "schuh", "schal ", "mütze", "muetze", "handschuh",
     "socken", "t-shirt", "jeans", "sneaker", "bikini", "bademantel", "fleecedecke"]],

  // Drogerie & Kosmetik
  ["Drogerie & Kosmetik", "Parfum & Düfte",
    ["parfum", "eau de toilette", "eau de parfum"]],
  ["Drogerie & Kosmetik", "Gesundheit & Apotheke",
    ["arzneimittel", "vitamin", "augentropfen", "salbe", "verband", "pflaster",
     "monatshygiene", "tampon", "binde", "magnesium"]],
  ["Drogerie & Kosmetik", "Kosmetik & Make-up",
    ["make-up", "mascara", "lippenstift", "wimperntusche", "lidschatten", "rouge",
     "nagellack"]],
  ["Drogerie & Kosmetik", "Körperpflege",
    ["shampoo", "duschgel", "duschbad", "seife", "bodylotion", "creme", "zahnpasta",
     "haarspray", "after-shave", "after-sun", "sonnenmilch", "sonnenspray",
     "sonnencreme", "reinigungsmilch", "bodymilk", "serum", "rasierer", "deospray", "deoroller", "zahnbürste", "rasierklinge", "haarfarbe", "haarspülung", "taschentücher"]],

  // Haushalt & Reinigung
  ["Haushalt & Reinigung", "Waschmittel",
    ["waschmittel", "waschpulver", "weichspüler", "weichspueler", "fleckensalz"]],
  ["Haushalt & Reinigung", "Reinigung",
    ["allzweckreiniger", "wc-reiniger", "glasreiniger", "scheuermilch", "spülmittel",
     "spuelmittel", "fensterputz", "tabs", "toilettenpapier", "küchenrolle"]],
  ["Haushalt & Reinigung", "Küchenbedarf",
    ["geschirr", "besteck", "kochtopf", "pfanne", "auflaufform", "frischhalte",
     "backblech", "lunchbox", "gefrierbeutel", "alufolie"]],
  ["Haushalt & Reinigung", "Aufbewahrung",
    ["aufbewahr", "müllbeutel", "muellbeutel", "wäscheklammer", "abfalleimer", "abfallsack",
     "mülleimer", "muelleimer"]],

  // Getränke
  ["Getränke", "Wein & Sekt",
    ["wein ", "rotwein", "weißwein", "weisswein", "rosé", "sekt", "prosecco", "champagner"]],
  ["Getränke", "Bier",
    ["bier", "pilsener", "pilsner", "weizenbier", "radler", "altbier", "kölsch"]],
  ["Getränke", "Spirituosen",
    ["vodka", "wodka", "gin ", "rum ", "whisky", "whiskey", "likör", "likoer", "tequila"]],
  ["Getränke", "Kaffee & Tee",
    ["kaffee", "espresso", "kapsel", "jacobs", "tchibo", "dallmayr", "lavazza", "kaffeepads", "filterkaffee", "tee ", "kräutertee", "kraeutertee"]],
  ["Getränke", "Wasser & Säfte",
    ["mineralwasser", "wasser ", "saft", "schorle", "limonade", "eistee", "fassbrause"]],

  // Lebensmittel
  ["Lebensmittel", "Tiefkühl",
    ["tiefkühl", "tiefkuehl", "tk-pizza", "frosta", "pizza", "pommes"]],
  ["Lebensmittel", "Fisch",
    ["lachs", "forelle", "seelachs", "thunfisch", "kabeljau", "fischstäbchen",
     "fischstaebchen", "garnele", "shrimp"]],
  ["Lebensmittel", "Fleisch & Wurst",
    ["fleisch", "salami", "schinken", "wurst", "würstchen", "hähnchen", "haehnchen", "rinder",
     "schwein", "putenbrust", "hackfleisch", "bratwurst", "leberwurst", "fleischkäse", "leberkäse", "kassler", "kotelett", "steak"]],
  ["Lebensmittel", "Milchprodukte & Käse",
    ["mozzarella", "käse", "kaese", "joghurt", "butter ", "milch ", "vollmilch",
     "h-milch", "sahne ", "quark", "frischkäse", "frischkaese", "emmentaler",
     "gouda", "feta", "eier "]],
  ["Lebensmittel", "Brot & Backwaren",
    ["brot ", "brötchen", "broetchen", "baguette", "toast ", "stollen", "lebkuchen",
     "croissant", "brezel"]],
  ["Lebensmittel", "Süßwaren & Snacks",
    ["schokolade", "praline", "keks ", "bonbon", "chips ", "salzstang", "gummibär",
     "gummibaer", "müsliriegel", "muesliriegel", "eis ", "eiscreme", "lindt", "duplo", "raffaello", "nutella", "nüsse", "erdnüsse", "studentenfutter"]],
  ["Lebensmittel", "Obst & Gemüse",
    ["apfel", "banane", "orange", "zitrone", "kirsche", "erdbeere", "tomate", "gurke",
     "kartoffel", "paprika", "brokkoli", "kohl ", "salat ", "ananas", "avocado"]],
  ["Lebensmittel", "Grundnahrung & Konserven",
    ["reis ", "nudeln", "pasta", "spaghetti", "mehl ", "zucker", "salz ", "gewürz",
     "gewuerz", "essig", "öl ", "oel ", "olivenöl", "olivenoel", "ketchup", "senf",
     "müsli", "muesli", "cornflakes", "haferflocken", "honig", "marmelade",
     "konserve", "antipasti", "mayonnaise", "konfitüre"]],

  // Sonstiges
  ["Sonstiges", "Auto & Mobilität",
    ["autopflege", "autozubehör", "autozubehoer", "scheibenwischer", "winterreifen",
     "sommerreifen", "motoröl", "motoroel"]],
  ["Sonstiges", "Büro & Schreibwaren",
    ["büromaterial", "bueromaterial", "schreibwaren", "kugelschreiber", "ordner ",
     "aktenschrank", "druckerpapier", "tintenpatron"]],
];

// ── 3. Fallback: noisy kaufDA-category keyword rules ─────────────────────────
// Same shape as TITLE_RULES, kept narrower since the category column is just
// a single keyword and we already missed on the title.
const CATEGORY_RULES: readonly Rule[] = [
  ["Baby & Kind", "Spielzeug", ["baby", "kinder", "fasching"]],
  ["Tier", "Katze", ["katze", "katzen"]],
  ["Tier", "Hund", ["hund"]],
  ["Tier", "Sonstige Tiere", ["haustier", "vogel"]],
  ["Garten & Heimwerken", "Gartenwerkzeug",
    ["akku-rasenmaeher", "rasenmaeher", "akku-heckenschere", "heckenscher",
     "akku-kettensaege", "akku-gartenschere"]],
  ["Garten & Heimwerken", "Pflanzen & Garten",
    ["azalee", "apfelbaum", "aster", "blumenkasten", "blumenampel"]],
  ["Garten & Heimwerken", "Gartenmöbel",
    ["ampelschirm", "faltpavillon", "feuerschale", "auflagenbox", "abdeckhaube",
     "abdeckplane", "anzuendkamin", "briketts"]],
  ["Garten & Heimwerken", "Werkzeug & Heimwerken",
    ["akkuschrauber", "akku-bohrschrauber", "bohrmaschine", "elektrowerkzeug",
     "fliesen", "eisenwaren", "alpina", "farbroller"]],
  ["Elektronik & Multimedia", "TV & Audio", ["fernsehsessel", "fernseher"]],
  ["Elektronik & Multimedia", "Haushaltsgeräte",
    ["akkustaubsauger", "fritteuse", "allesschneider", "fenstersauger"]],
  ["Elektronik & Multimedia", "Sonstige Elektronik",
    ["akku ", "fernglas", "epson", "ladegeraet", "elektronische-dartscheibe", "funkwanduhr"]],
  ["Elektronik & Multimedia", "Smartphone & Tablet", ["apple", "android-tablet"]],
  ["Mode, Sport & Freizeit", "Sport & Fitness", ["fitnessgeraete", "fussball"]],
  ["Mode, Sport & Freizeit", "Spielzeug & Hobby", ["fahrrad", "elektrofahrrad", "elektrorad"]],
  ["Mode, Sport & Freizeit", "Kleidung & Schuhe",
    ["adidas", "aigner", "aquaschuhe", "arbeitshose", "badetuch", "fleecedecke"]],
  ["Drogerie & Kosmetik", "Gesundheit & Apotheke",
    ["arzneimittel", "augentropfen", "altapharma", "erste-hilfe"]],
  ["Drogerie & Kosmetik", "Kosmetik & Make-up", ["essence", "artdeco", "elnett"]],
  ["Drogerie & Kosmetik", "Körperpflege",
    ["aloe-vera", "axe", "always", "einwegrasierer", "fusselrasierer", "after-sun",
     "after-shave"]],
  ["Haushalt & Reinigung", "Waschmittel", ["ariel", "ariel-waschpulver"]],
  ["Haushalt & Reinigung", "Reinigung", ["finish", "frosch", "febreze", "ajax", "ecover"]],
  ["Haushalt & Reinigung", "Küchenbedarf", ["besteck-set", "auflaufform"]],
  ["Haushalt & Reinigung", "Aufbewahrung",
    ["aufbewahrung", "aufbewahrungsbox", "aufbewahrungsdosen", "abfalleimer",
     "muelleimer", "fussmatte", "bettwaesche"]],
  ["Getränke", "Wein & Sekt",
    ["alkoholische-getraenke", "alkoholfreier-sekt", "alkoholfreier-wein",
     "freixenet-sekt", "metternich", "asti", "cinzano", "fruchtsecco"]],
  ["Getränke", "Bier",
    ["becks", "feldschloesschen", "flensburger-pilsener", "fassbier", "freiberger"]],
  ["Getränke", "Spirituosen",
    ["aperol", "aperitif", "absolut-vodka", "echter-nordhaeuser", "almdudler"]],
  ["Getränke", "Kaffee & Tee", ["filterkaffee", "espressobohnen"]],
  ["Getränke", "Wasser & Säfte",
    ["alkoholfreie-getraenke", "fanta", "fritz-kola", "afri-cola", "fassbrause",
     "apfelschorle", "apfelsaft", "orangensaft", "adelholzener", "arizona-eistee",
     "amecke", "appel", "albi", "ayran", "apfelwein"]],
  ["Lebensmittel", "Obst & Gemüse",
    ["apfel", "aprikosen", "avocado", "ananas", "auberginen", "elstar"]],
  ["Lebensmittel", "Fisch", ["fisch", "fischstaebchen", "alaska-seelachs", "bio-lachs", "barsch", "forelle"]],
  ["Lebensmittel", "Fleisch & Wurst",
    ["fleisch", "edelsalami", "cordon-bleu", "fleischkaese", "eberswalder", "frikadellen"]],
  ["Lebensmittel", "Milchprodukte & Käse",
    ["emmentaler", "appenzeller", "esrom", "alpro", "almighurt", "actimel", "activia",
     "arla-kaergarden", "almette", "alpenhain", "butter", "mozzarella"]],
  ["Lebensmittel", "Brot & Backwaren", ["backwaren", "amerikaner", "apfeltasche"]],
  ["Lebensmittel", "Süßwaren & Snacks",
    ["ferrero", "ferrero-kuesschen", "funny-frisch", "amicelli", "alesto", "eiscreme",
     "florida-eis", "eclair", "chio"]],
  ["Lebensmittel", "Tiefkühl", ["frosta", "tiefkuehl"]],
  ["Lebensmittel", "Grundnahrung & Konserven",
    ["antipasti", "alnatura", "ajvar", "anis", "asia", "american-style", "tabasco",
     "tortilla", "frischer-pasta", "express-reis", "fertiggericht", "fruehstueck",
     "flammkuchen", "frosch", "aspik", "eiersalat", "appel", "apfelringe"]],
  ["Sonstiges", "Auto & Mobilität",
    ["autopflege", "autozubehoer", "autositzbezuege", "auto-sonnenschutz"]],
  ["Sonstiges", "Büro & Schreibwaren", ["aktenschrank", "akten"]],
];

function normalize(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .toLowerCase()
    .replace(/[-_./]/g, " ")
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    .replace(/\s+/g, " ")
    .trim();
}

type Keyword = {
  bucket: Bucket;
  subcategory: string;
  k: string;
  /** "whole word / compound tail only" — never a free substring */
  bounded: boolean;
  /** position in the rule list — earlier rules are more specific */
  order: number;
};

function compile(rules: readonly Rule[]): Keyword[] {
  let order = 0;
  return rules.flatMap(([bucket, subcategory, keywords]) =>
    keywords.map((kw) => ({
      bucket,
      subcategory,
      k: normalize(kw),
      // A trailing space in the rule = "whole word only" ("wein " must not
      // match "Weinbergschnecken", "schal " must not match "Schalotten").
      bounded: kw.endsWith(" ") || normalize(kw).length <= 4,
      order: order++,
    })),
  );
}

// Words that end in a product keyword but are never that product.
const NOT_PRODUCT_WORD = /(?:preis|serum|zentrum|origin)$/;

/** Best keyword for one word: exact match or the longest compound tail. */
function bestForWord(word: string, rules: readonly Keyword[]): Keyword | null {
  let best: Keyword | null = null;
  const tailOk = !NOT_PRODUCT_WORD.test(word);
  for (const r of rules) {
    if (r.k.includes(" ")) continue;
    const hit = word === r.k || (tailOk && r.k.length >= 3 && word.endsWith(r.k));
    if (hit && (!best || r.k.length > best.k.length)) best = r;
  }
  return best;
}

/**
 * German puts the head noun LAST in a compound: "Tomatenketchup" is ketchup,
 * "Blumenkohl" is kohl, "Kartoffelchips" is chips. So, most specific first:
 *   1. multi-word phrases ("eau de toilette") and, per title word, the exact
 *      keyword or longest compound tail. Between words, rule order decides.
 *   2. otherwise a free substring (unbounded keywords > 4 chars), rule order.
 * Before this, "Tomatenketchup" landed in Obst & Gemüse via "tomate".
 */
function matchRules(text: string, rules: readonly Keyword[]): Classification | null {
  if (!text) return null;
  const padded = ` ${text} `;
  let best: Keyword | null = null;
  const consider = (r: Keyword | null) => {
    if (r && (!best || r.order < best.order)) best = r;
  };

  for (const r of rules) if (r.k.includes(" ") && padded.includes(` ${r.k} `)) consider(r);
  for (const w of text.split(" ")) if (w) consider(bestForWord(w, rules));
  if (best) return { bucket: (best as Keyword).bucket, subcategory: (best as Keyword).subcategory };

  for (const r of rules) {
    if (!r.bounded && text.includes(r.k)) return { bucket: r.bucket, subcategory: r.subcategory };
  }
  return null;
}

const TITLE_KEYWORDS = compile(TITLE_RULES);
const CATEGORY_KEYWORDS = compile(CATEGORY_RULES);

/**
 * Classify using title (primary) + kaufda category (fallback).
 *
 * The legacy single-arg form `classify(rawCategory)` is still supported for
 * code paths that don't have the title at hand.
 */
export function classify(
  titleOrCategory: string | null | undefined,
  kaufdaCategory?: string | null,
): Classification {
  const title = titleOrCategory ?? "";

  // 1. Hard brand rules on the RAW title (regex, not normalized — keeps "Apple TV"
  //    distinct from "apfel"). Bail immediately on first match.
  for (const [bucket, subcategory, re] of HARD_RULES) {
    if (re.test(title)) return { bucket, subcategory };
  }

  // 2. Title-keyword rules on normalized title.
  const normTitle = normalize(title);
  const titleHit = matchRules(normTitle, TITLE_KEYWORDS);
  if (titleHit) return titleHit;

  // 3. Fallback: normalized kaufda category.
  const normCat = normalize(kaufdaCategory ?? titleOrCategory);
  const catHit = matchRules(normCat, CATEGORY_KEYWORDS);
  if (catHit) return catHit;

  return { bucket: "Sonstiges", subcategory: "Sonstige" };
}

// Convenience wrapper used by older callers that only want the bucket.
export function mapToBucket(rawCategory: string | null | undefined): Bucket {
  return classify(rawCategory).bucket;
}
