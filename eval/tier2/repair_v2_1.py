"""Deterministic v2.1 repair of Team B's v2.0-draft Tier-2 specs (data only; no inference, no scoring).

Reads Team B's delivery READ-ONLY and writes a new, versioned tree (refuses to write into a non-empty directory):

    <out>/dev/pair_specs_v2_1.json         126 specs, 18 repaired, every spec in the dev split
    <out>/dev/splits_v2_1.jsonl            split rows ("dev"); the 30 exposed Team B test rows keep ``origin_split``
    <out>/banks/distractors_v2_1.json  hi (v1 bank minus 2 colliding turns) + mr + gu distractor bank
    <out>/CHANGELOG_v2_1.json              per-spec before/after, reason and linguistic-confidence flag
    <out>/heldout_sealed/...               Hindi reserve set, UNBLINDED (see README_v2_1.md and heldout_integrity_v2_1.py)

Nothing here was reviewed by a native speaker. Every changed Marathi/Gujarati string is flagged ``needs_native_review``.
    python -m tier2.repair_v2_1 --delivery data/team_b_delivery --out data/tier2_v2_1
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

SRC_DEFAULT = "data/team_b_delivery"
CITY = {"pune": ["pune", "पुणे"], "nashik": ["nashik", "नाशिक"], "mumbai": ["mumbai", "मुंबई"], "delhi": ["delhi", "दिल्ली"],
        "nagpur": ["nagpur", "नागपुर"], "patna": ["patna", "पटना"], "agra": ["agra", "आगरा"], "kanpur": ["kanpur", "कानपुर"],
        "ranchi": ["ranchi", "रांची"], "ahmedabad": ["ahmedabad", "અમદાવાદ"], "surat": ["surat", "સુરત"], "rajkot": ["rajkot", "રાજકોટ"],
        "delhi_gu": ["delhi", "દિલ્હી"], "mumbai_gu": ["mumbai", "મુંબઈ"]}
DAY = {"somvar": ["somvar", "सोमवार"], "mangalvar": ["mangalvar", "मंगलवार"], "budhvar": ["budhvar", "बुधवार"], "guruvar": ["guruvar", "गुरुवार"],
       "shukravar": ["shukravar", "शुक्रवार"], "shanivar": ["shanivar", "शनिवार"], "ravivar": ["ravivar", "रविवार"]}
MONTH = {"may": ["may", "मई"], "august": ["august", "अगस्त"], "march": ["march", "मार्च"], "november": ["november", "नवंबर"]}


def A(*groups):
    return [list(g) for g in groups]


def qa_diff(qa, qb, sa, fa, sb, fb):
    return [{"role": "a", "question": qa, "slots": [sa], "forbidden": [fa]}, {"role": "b", "question": qb, "slots": [sb], "forbidden": [fb]}]


def qa_ab(q, *slots):
    return [{"role": "ab", "question": q, "slots": [list(s) for s in slots], "forbidden": []}]


# spec id -> (changes, reason, confidence). "native" True = the changed text is Marathi/Gujarati and unverified.
PATCHES = {
    "t2s_v2_0109": (dict(text_b="Rahul, tu Pune kab ja raha hai", fact_b={"attribute": "travel_city", "value": "Pune"},
                         qa=qa_diff("Sharma uncle kahan ja rahe hain?", "Rahul kahan ja raha hai?", CITY["delhi"], CITY["pune"], CITY["pune"], CITY["delhi"])),
                    "both sides carried the same city, so QA could not tell the two addressees apart; b's city changed (gold unchanged)", "high", False),
    "t2s_v2_0111": (dict(text_b="Bhai, tu college kab aayega", fact_b={"attribute": "arrival_place", "value": "college"},
                         qa=qa_diff("Principal sahab kahan aayenge?", "Bhai kahan aayega?", ["school", "स्कूल"], ["college", "कॉलेज"], ["college", "कॉलेज"], ["school", "स्कूल"])),
                    "same arrival place on both sides; b's place changed", "high", False),
    "t2s_v2_0112": (dict(text_b="Yaar, tune photo dekhi", fact_a={"attribute": "viewed_item", "value": "report"}, fact_b={"attribute": "viewed_item", "value": "photo"},
                         qa=qa_diff("Doctor sahab ne kya dekha?", "Yaar ne kya dekha?", ["report", "रिपोर्ट"], ["photo", "फोटो"], ["photo", "फोटो"], ["report", "रिपोर्ट"])),
                    "answer alias 'dekhi' was a verb form present on both sides; the viewed item now differs and is the answer", "high", False),
    "t2s_v2_0113": (dict(text_b="Chhotu, tujhe Nagpur jaana hai", fact_b={"attribute": "travel_city", "value": "Nagpur"},
                         qa=qa_diff("Mishra ji ko kahan jaana hai?", "Chhotu ko kahan jaana hai?", CITY["pune"], CITY["nagpur"], CITY["nagpur"], CITY["pune"])),
                    "same city on both sides; b's city changed", "high", False),
    "t2s_v2_0115": (dict(text_a="Amit jo Delhi mein rehta hai uska phone somvar ko aaya", text_b="अमित जो Mumbai mein rehta hai uska phone shukravar ko aaya",
                         fact_a={"attribute": "call_day", "value": "somvar"}, fact_b={"attribute": "call_day", "value": "shukravar"},
                         qa=qa_diff("Delhi wale Amit ka phone kis din aaya?", "Mumbai wale Amit ka phone kis din aaya?", DAY["somvar"], DAY["shukravar"], DAY["shukravar"], DAY["somvar"])),
                    "the question named the city it asked for and the sentences differed in nothing else; a call weekday (v1 attribute) is added to both sides", "high", False),
    "t2s_v2_0129": (dict(text_a="आई, तू Pune ला कधी येणार", text_b="आई, तुम्ही Nashik ला कधी येणार",
                         fact_a={"attribute": "visit_city", "value": "Pune"}, fact_b={"attribute": "visit_city", "value": "Nashik"},
                         qa=qa_ab("Aai kuthe kuthe yenar?", CITY["pune"], CITY["nashik"])),
                    "gold-same pair carried an identical fact on both sides and the question contained it; each side now carries a different city and the question needs both", "medium", True),
    "t2s_v2_0130": (dict(text_b="बाबा, तुम्ही Nashik ला गेलात का", fact_b={"attribute": "visit_city", "value": "Nashik"},
                         qa=qa_ab("Baba kuthe kuthe gele?", CITY["pune"], CITY["nashik"])),
                    "as 0129", "medium", True),
    "t2s_v2_0131": (dict(text_a="आजी, तुम्ही Pune मधे कशा आहात", text_b="आजी, तू Mumbai मधे कशी आहेस",
                         fact_a={"attribute": "location", "value": "Pune"}, fact_b={"attribute": "location", "value": "Mumbai"},
                         qa=qa_ab("Aaji kuthe kuthe aahe?", CITY["pune"], CITY["mumbai"])),
                    "answer 'aaji' was the vocative already in the question; no distinguishing fact existed", "low", True),
    "t2s_v2_0132": (dict(text_b="विकास काका, तू Nashik ला आलास का", fact_b={"attribute": "visit_city", "value": "Nashik"},
                         qa=qa_ab("Vikas kaka kuthe kuthe aale?", CITY["mumbai"], CITY["nashik"])),
                    "as 0129", "medium", True),
    "t2s_v2_0133": (dict(text_b="रवी, तू college ला कधी येणार", fact_b={"attribute": "arrival_place", "value": "college"},
                         qa=qa_diff("Saheb kuthe yenar?", "Ravi kuthe yenar?", ["office", "ऑफिस"], ["college", "कॉलेज"], ["college", "कॉलेज"], ["office", "ऑफिस"])),
                    "same place on both sides; b's place changed", "medium", True),
    "t2s_v2_0134": (dict(text_b="सीमा ताई, तुला photo हवा आहे का", fact_b={"attribute": "request", "value": "photo"},
                         qa=qa_diff("Joshi madam la kay hava aahe?", "Seema tai la kay hava aahe?", ["report", "रिपोर्ट"], ["photo", "फोटो"], ["photo", "फोटो"], ["report", "रिपोर्ट"])),
                    "same requested item on both sides; b's item changed (loan noun assumed masculine like 'report', agreement 'हवा' kept)", "medium", True),
    "t2s_v2_0135": (dict(text_b="राहुल, तू class ला येशील का", fact_b={"attribute": "event", "value": "class"},
                         qa=qa_diff("Sharma sir kuthe yetil?", "Rahul kuthe yeil?", ["meeting", "मीटिंग"], ["class", "क्लास"], ["class", "क्लास"], ["meeting", "मीटिंग"])),
                    "same event on both sides; b's event changed", "medium", True),
    "t2s_v2_0152": (dict(text_b="બા, તું Surat ક્યારે આવીશ", fact_b={"attribute": "visit_city", "value": "Surat"},
                         qa=qa_ab("Ba kyan kyan aavse?", CITY["ahmedabad"], CITY["surat"])),
                    "gold-same pair carried an identical fact on both sides and the question contained it; b's city changed, question needs both", "medium", True),
    "t2s_v2_0153": (dict(text_b="પપ્પા, તું Mumbai ગયો હતો", fact_b={"attribute": "visit_city", "value": "Mumbai"},
                         qa=qa_ab("Pappa kyan kyan gaya hata?", CITY["delhi_gu"], CITY["mumbai_gu"])),
                    "as 0152", "medium", True),
    "t2s_v2_0154": (dict(text_b="રમેશ દાદા, તું message ક્યારે કરીશ", fact_a={"attribute": "action", "value": "phone"}, fact_b={"attribute": "action", "value": "message"},
                         qa=qa_ab("Ramesh dada shu shu karse?", ["phone", "ફોન"], ["message", "મેસેજ"])),
                    "identical action on both sides; b's light-verb object changed (phone->message)", "medium", True),
    "t2s_v2_0155": (dict(text_b="ભાઈ, તું Rajkot ક્યારે આવીશ", fact_b={"attribute": "visit_city", "value": "Rajkot"},
                         qa=qa_diff("Sheth kyan aavse?", "Bhai kyan aavse?", CITY["surat"], CITY["rajkot"], CITY["rajkot"], CITY["surat"])),
                    "same city on both sides; b's city changed", "medium", True),
    "t2s_v2_0156": (dict(text_b="યાર, તને photo જોઈએ છે", fact_b={"attribute": "request", "value": "photo"},
                         qa=qa_diff("Saheb ne shu joiye che?", "Yaar ne shu joiye che?", ["report", "રિપોર્ટ"], ["photo", "ફોટો"], ["photo", "ફોટો"], ["report", "રિપોર્ટ"])),
                    "same item on both sides; b's item changed ('જોઈએ' is invariant)", "medium", True),
    "t2s_v2_0157": (dict(text_b="દોસ્ત, તેં paper check કર્યું", fact_b={"attribute": "action", "value": "paper check"},
                         qa=qa_diff("Teacher e shu check karyu?", "Dost e shu check karyu?", ["homework", "હોમવર્ક"], ["paper", "પેપર"], ["paper", "પેપર"], ["homework", "હોમવર્ક"])),
                    "same object on both sides; b's object changed", "medium", True),
}

# ------------------------------------------------------------------ distractor bank (Marathi, Gujarati): hand-authored, neutral
MR_USER = [
    "आज दिवसभर खूप काम होतं", "उद्या कदाचित पाऊस पडेल", "मी नवीन इअरबड्स मागवले आहेत", "रात्रीच्या जेवणाला पनीर केलं होतं",
    "मला सकाळी लवकर उठावं लागतं", "सध्या मी रोज फिरायला जातो", "माझ्या लॅपटॉपची बॅटरी लवकर संपते", "आज चहा थोडा जास्त झाला",
    "मला नवीन पुस्तक वाचायचं आहे", "घरी नवीन झाड लावलं आहे", "आज खूप गरमी होत आहे", "मी संध्याकाळी थोडा व्यायाम करतो",
    "भाजी घ्यायला बाजारात जायचं आहे", "मोबाईलचा चार्जर सापडत नाहीये", "आज रात्री लवकर झोपायचं आहे",
    "Aaj divasbhar khup kaam hota", "Mala ek navin gaana aavadla aahe", "Sandhyakali chaha pyaycha aahe", "Mi ata jevan banvat aahe",
    "Ya mahinyat khup paus padla", "Mala nave shoes ghyayche aahet", "Aajkal mi roj cycle chalvto", "Wifi khup halu chalat aahe",
    "Mala ek chhota break ghyaycha aahe", "Aaj bhaji khup chhan zali", "Mi navin recipe try keli", "Ratri film baghayche aahe",
    "Mala thoda ukaadha vatat aahe", "Aaj sakali lavkar uthlo", "Ghari nave curtains lavle aahet"]
GU_USER = [
    "આજે આખો દિવસ કામ રહ્યું", "કાલે કદાચ વરસાદ પડશે", "મેં નવા ઇયરબડ્સ મંગાવ્યા છે", "રાત્રે જમવામાં પનીર બનાવ્યું હતું",
    "મારે સવારે વહેલા ઊઠવું પડે છે", "હમણાં હું રોજ ફરવા જાઉં છું", "મારા લેપટોપની બેટરી જલદી ખતમ થઈ જાય છે", "આજે ચા થોડી વધારે થઈ ગઈ",
    "મારે નવું પુસ્તક વાંચવું છે", "ઘરે નવો છોડ વાવ્યો છે", "આજે બહુ ગરમી છે", "હું સાંજે થોડી કસરત કરું છું",
    "શાક લેવા બજારમાં જવું છે", "મોબાઇલનું ચાર્જર મળતું નથી", "આજે રાત્રે વહેલા સૂવું છે",
    "Aaje divas bhar kaam rahyu", "Mane ek navu gaanu gamyu che", "Saanje chaa pivi che", "Hu hamna jaman banavu chu",
    "Aa mahine ghano varsaad padyo", "Mare nava shoes levana che", "Hamna hu roj cycle chalavu chu", "Wifi bahu dhimu chaale che",
    "Mare thodo break levo che", "Aaje shaak bahu saras bani", "Me navi recipe try kari", "Raatre film jovi che",
    "Mane thodo thaak lagyo che", "Aaje savare vahela uthyo", "Gharma navi curtain lagavi che"]

HI_DROP = {"Maine online class ke liye register kiya hai", "Kal ek meeting aage badh gayi"}

# ------------------------------------------------------------------ Hindi RESERVE set (unblinded). Written by the agent after it had read the exposed
# Team B test labels; several frames derive from exposed items (see heldout_integrity_v2_1.py). NOT an independent or blind test set.
_h = lambda sid, rel, cls, a, b, ma, mb, fa, fb, qa: {"spec_id": sid, "source": "v2.1-heldout-claude-authored", "relation": rel, "distinction_class": cls,
                                                    "language": "hi", "text_a": a, "text_b": b, "marker_a": ma, "marker_b": mb, "fact_a": fa, "fact_b": fb, "qa": qa}
_f = lambda attr, val: {"attribute": attr, "value": val}
HELDOUT = [
    _h("t2s_v2h_0001", "different", "kinship", "Meri chachi Patna mein rehti hai", "Meri mausi Agra mein rehti hai", "chachi", "mausi", _f("residence_city", "Patna"), _f("residence_city", "Agra"),
       qa_diff("Meri chachi kahan rehti hain?", "Meri mausi kahan rehti hain?", CITY["patna"], CITY["agra"], CITY["agra"], CITY["patna"])),
    _h("t2s_v2h_0002", "different", "kinship", "Meri mami Kanpur aa rahi hai", "Meri bua Ranchi aa rahi hai", "mami", "bua", _f("arrival_city", "Kanpur"), _f("arrival_city", "Ranchi"),
       qa_diff("Meri mami kahan aa rahi hain?", "Meri bua kahan aa rahi hain?", CITY["kanpur"], CITY["ranchi"], CITY["ranchi"], CITY["kanpur"])),
    _h("t2s_v2h_0003", "different", "kinship", "Meri dadi ka phone somvar ko aaya", "Meri nani ka phone guruvar ko aaya", "dadi", "nani", _f("call_day", "somvar"), _f("call_day", "guruvar"),
       qa_diff("Meri dadi ka phone kis din aaya?", "Meri nani ka phone kis din aaya?", DAY["somvar"], DAY["guruvar"], DAY["guruvar"], DAY["somvar"])),
    _h("t2s_v2h_0004", "different", "kinship", "Meri bua ka phone mangalvar ko aaya", "Meri chachi ka phone shanivar ko aaya", "bua", "chachi", _f("call_day", "mangalvar"), _f("call_day", "shanivar"),
       qa_diff("Meri bua ka phone kis din aaya?", "Meri chachi ka phone kis din aaya?", DAY["mangalvar"], DAY["shanivar"], DAY["shanivar"], DAY["mangalvar"])),
    _h("t2s_v2h_0005", "same", "kinship", "Meri nani, yaani Savita ji, Patna mein rehti hai", "Savita ji ka birthday May mein hai", "nani", "Savita ji", _f("residence_city", "Patna"), _f("birthday_month", "May"),
       qa_ab("Savita ji kahan rehti hain aur unka birthday kab hai?", CITY["patna"], MONTH["may"])),
    _h("t2s_v2h_0006", "same", "kinship", "Chachi Sunita ne mujhe Agra mein gift diya", "Sunita aunty ne mujhe ravivar ko call kiya", "chachi", "Sunita aunty", _f("gift_city", "Agra"), _f("call_day", "ravivar"),
       qa_ab("Sunita ne kahan gift diya aur kis din call kiya?", CITY["agra"], DAY["ravivar"])),
    _h("t2s_v2h_0007", "same", "kinship", "Mausi Rekha Ranchi mein rehti hain", "Maa ki behen Rekha ka birthday August mein hai", "mausi", "maa ki behen", _f("residence_city", "Ranchi"), _f("birthday_month", "August"),
       qa_ab("Rekha kahan rehti hain aur unka birthday kab hai?", CITY["ranchi"], MONTH["august"])),
    _h("t2s_v2h_0008", "same", "kinship", "Bua Meena Kanpur se aayi hain", "Papa ki behen Meena budhvar ko pahunchi", "bua", "papa ki behen", _f("origin_city", "Kanpur"), _f("arrival_day", "budhvar"),
       qa_ab("Meena kahan se aayi aur kis din pahunchi?", CITY["kanpur"], DAY["budhvar"])),
    _h("t2s_v2h_0009", "same", "honorific_register", "Maa, tum Patna se kab aa rahi ho", "Maa, aap ravivar ko ghar aayengi", "tum", "aap", _f("origin_city", "Patna"), _f("arrival_day", "ravivar"),
       qa_ab("Maa kahan se aa rahi hain aur kis din ghar aayengi?", CITY["patna"], DAY["ravivar"])),
    _h("t2s_v2h_0010", "same", "honorific_register", "Papa, tum Agra ja rahe ho", "Papa, aap shukravar ko nikalenge", "tum", "aap", _f("travel_city", "Agra"), _f("departure_day", "shukravar"),
       qa_ab("Papa kahan ja rahe hain aur kis din nikalenge?", CITY["agra"], DAY["shukravar"])),
    _h("t2s_v2h_0011", "same", "honorific_register", "Sunita didi, tum Kanpur mein rehti ho", "Sunita didi, aap budhvar ko phone karengi", "tum", "aap", _f("residence_city", "Kanpur"), _f("call_day", "budhvar"),
       qa_ab("Sunita didi kahan rehti hain aur kis din phone karengi?", CITY["kanpur"], DAY["budhvar"])),
    _h("t2s_v2h_0012", "same", "honorific_register", "Papa, tumne Ranchi mein mera result dekha", "Papa, aapne somvar ko mera result dekha", "tumne", "aapne", _f("seen_city", "Ranchi"), _f("seen_day", "somvar"),
       qa_ab("Papa ne mera result kahan aur kis din dekha?", CITY["ranchi"], DAY["somvar"])),
    _h("t2s_v2h_0013", "different", "honorific_register", "Verma uncle, aap Patna kab ja rahe hain", "Sonu, tu Agra kab ja raha hai", "aap", "tu", _f("travel_city", "Patna"), _f("travel_city", "Agra"),
       qa_diff("Verma uncle kahan ja rahe hain?", "Sonu kahan ja raha hai?", CITY["patna"], CITY["agra"], CITY["agra"], CITY["patna"])),
    _h("t2s_v2h_0014", "different", "honorific_register", "Professor sahab, aapko Kanpur jaana hai", "Bhai, tujhe Ranchi jaana hai", "aapko", "tujhe", _f("travel_city", "Kanpur"), _f("travel_city", "Ranchi"),
       qa_diff("Professor sahab ko kahan jaana hai?", "Bhai ko kahan jaana hai?", CITY["kanpur"], CITY["ranchi"], CITY["ranchi"], CITY["kanpur"])),
    _h("t2s_v2h_0015", "different", "honorific_register", "Manager sahab, aapne Agra mein meeting rakhi", "Yaar, tune Patna mein meeting rakhi", "aapne", "tune", _f("meeting_city", "Agra"), _f("meeting_city", "Patna"),
       qa_diff("Manager sahab ne meeting kahan rakhi?", "Yaar ne meeting kahan rakhi?", CITY["agra"], CITY["patna"], CITY["patna"], CITY["agra"])),
    _h("t2s_v2h_0016", "different", "honorific_register", "Gupta madam, aap budhvar ko aayengi", "Pinky, tu shukravar ko aayegi", "aap", "tu", _f("arrival_day", "budhvar"), _f("arrival_day", "shukravar"),
       qa_diff("Gupta madam kis din aayengi?", "Pinky kis din aayegi?", DAY["budhvar"], DAY["shukravar"], DAY["shukravar"], DAY["budhvar"])),
    _h("t2s_v2h_0017", "different", "contextual_qualifier", "Rohit jo Patna mein rehta hai uska phone somvar ko aaya", "रोहित जो Agra mein rehta hai uska phone shukravar ko aaya", "Rohit", "रोहित",
       _f("call_day", "somvar"), _f("call_day", "shukravar"),
       qa_diff("Patna wale Rohit ka phone kis din aaya?", "Agra wale Rohit ka phone kis din aaya?", DAY["somvar"], DAY["shukravar"], DAY["shukravar"], DAY["somvar"])),
    _h("t2s_v2h_0018", "different", "contextual_qualifier", "Meri office wali Sunita Kanpur mein rehti hai", "Meri school wali Sunita Ranchi mein rehti hai", "office wali Sunita", "school wali Sunita",
       _f("residence_city", "Kanpur"), _f("residence_city", "Ranchi"),
       qa_diff("Meri office wali Sunita kahan rehti hai?", "Meri school wali Sunita kahan rehti hai?", CITY["kanpur"], CITY["ranchi"], CITY["ranchi"], CITY["kanpur"])),
    _h("t2s_v2h_0019", "different", "contextual_qualifier", "Gym wali Anita budhvar ko aayi", "Class wali अनीता ravivar ko aayi", "Anita", "अनीता", _f("arrival_day", "budhvar"), _f("arrival_day", "ravivar"),
       qa_diff("Gym wali Anita kis din aayi?", "Class wali Anita kis din aayi?", DAY["budhvar"], DAY["ravivar"], DAY["ravivar"], DAY["budhvar"])),
    _h("t2s_v2h_0020", "different", "contextual_qualifier", "Meri padosan Seema Agra se aayi hai", "Meri colleague सीमा Patna se aayi hai", "Seema", "सीमा", _f("origin_city", "Agra"), _f("origin_city", "Patna"),
       qa_diff("Meri padosan Seema kahan se aayi hai?", "Meri colleague Seema kahan se aayi hai?", CITY["agra"], CITY["patna"], CITY["patna"], CITY["agra"])),
    _h("t2s_v2h_0021", "same", "name_variant", "Sunita ka birthday May mein hai", "सुनीता Patna mein rehti hai", "Sunita", "सुनीता", _f("birthday_month", "May"), _f("residence_city", "Patna"),
       qa_ab("Sunita ka birthday kab hai aur woh kahan rehti hai?", MONTH["may"], CITY["patna"])),
    _h("t2s_v2h_0022", "same", "name_variant", "Mohit ka birthday August mein hai", "मोहित Agra mein rehta hai", "Mohit", "मोहित", _f("birthday_month", "August"), _f("residence_city", "Agra"),
       qa_ab("Mohit ka birthday kab hai aur woh kahan rehta hai?", MONTH["august"], CITY["agra"])),
    _h("t2s_v2h_0023", "same", "name_variant", "Divya ka birthday March mein hai", "दिव्या Kanpur mein rehti hai", "Divya", "दिव्या", _f("birthday_month", "March"), _f("residence_city", "Kanpur"),
       qa_ab("Divya ka birthday kab hai aur woh kahan rehti hai?", MONTH["march"], CITY["kanpur"])),
    _h("t2s_v2h_0024", "same", "name_variant", "Sandeep ka birthday November mein hai", "संदीप Ranchi mein rehta hai", "Sandeep", "संदीप", _f("birthday_month", "November"), _f("residence_city", "Ranchi"),
       qa_ab("Sandeep ka birthday kab hai aur woh kahan rehta hai?", MONTH["november"], CITY["ranchi"])),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def dumpl(p: Path, rows) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--delivery", type=Path, default=Path(SRC_DEFAULT))
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.out.exists() and any(a.out.iterdir()):
        raise SystemExit(f"{a.out} is not empty; refusing to overwrite")
    d = a.delivery
    src = json.loads((d / "banks/pair_specs_v2.json").read_text(encoding="utf-8"))
    splits = {}
    for name in ("dev", "test"):
        for line in (d / f"data/tier2_v2_{name}_gold.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            splits[r["eval_pair_id"]] = {**r, "split": name}
    specs, changelog = [], []
    for s in src["specs"]:
        s2 = copy.deepcopy(s)
        if s["spec_id"] in PATCHES:
            ch, why, conf, native = PATCHES[s["spec_id"]]
            before = {k: s[k] for k in ch}
            s2.update(ch)
            s2["repair"] = {"version": "2.1", "reason": why, "linguistic_confidence": conf, "needs_native_review": native}
            changelog.append({"spec_id": s["spec_id"], "language": s["language"], "relation": s["relation"], "class": s["distinction_class"],
                              "origin_split": splits[s["spec_id"]]["split"], "reason": why, "linguistic_confidence": conf,
                              "needs_native_review": native, "before": before, "after": {k: s2[k] for k in ch}})
        specs.append(s2)
    rows = [{"eval_pair_id": s["spec_id"], "relation": s["relation"], "distinction_class": s["distinction_class"], "language": s["language"],
             "split": "dev", "origin_split": ("team_b_test_EXPOSED" if splits[s["spec_id"]]["split"] == "test" else "dev"),
             "source": splits[s["spec_id"]].get("source")} for s in specs]
    out = a.out
    dump(out / "dev/pair_specs_v2_1.json", {"spec_version": "2.1", "description": "Team B v2.0-draft specs with the 18 QA-contract failures repaired; every spec is dev "
                                            "(the 30 Team B test rows were exposed in VERIFICATION_PROMPT.md).", "provenance": src.get("provenance"),
                                            "derived_from_sha256": sha(d / "banks/pair_specs_v2.json"), "specs": specs})
    dumpl(out / "dev/splits_v2_1.jsonl", rows)
    dump(out / "CHANGELOG_v2_1.json", changelog)
    asst = json.loads(Path("eval/tier2/banks/distractors.json").read_text(encoding="utf-8"))["assistant_turns"]["hi"]
    hi_all = json.loads(Path("eval/tier2/banks/distractors.json").read_text(encoding="utf-8"))["user_turns"]["hi"]
    hi_user = [t for t in hi_all if t not in HI_DROP]
    dump(out / "banks/distractors_v2_1.json", {
        "bank_version": "2.1", "status": "UNREVIEWED: mr/gu hand-authored by Claude, no native-speaker review; neutral content only",
        "description": "Marathi and Gujarati distractor turns for the Tier-2 v2 generator. Neutral daily-life statements, no kinship term, register pronoun, personal name, "
                       "city, weekday, month or QA value of any spec. Half native script, half Roman, mirroring the injected turns. Assistant turns are the Hindi "
                       "bank's language-neutral English acknowledgements, reused verbatim. Hindi = the frozen v1 Hindi bank minus the turns in "
                       "hi_user_turns_dropped (they contain a v2 QA value: 'meeting', 'class'); German is out of v2.",
        "hi_user_turns_dropped": sorted(HI_DROP),
        "user_turns": {"hi": hi_user, "mr": MR_USER, "gu": GU_USER},
        "assistant_turns": {"hi": copy.deepcopy(asst), "mr": copy.deepcopy(asst), "gu": copy.deepcopy(asst)}})
    hs = out / "heldout_sealed"
    dump(hs / "pair_specs_heldout_v1.json", {"spec_version": "heldout-1", "description": "Hindi held-out Tier-2 specs; evaluator-side, sealed until the freeze.", "specs": HELDOUT})
    dumpl(hs / "splits_heldout_v1.jsonl", [{"eval_pair_id": s["spec_id"], "relation": s["relation"], "distinction_class": s["distinction_class"],
                                            "language": s["language"], "split": "test", "source": s["source"]} for s in HELDOUT])
    files = sorted(p for p in out.rglob("*") if p.is_file())
    dump(out / "MANIFEST_v2_1.json", {"version": "2.1-draft", "status": "DRAFT (not frozen; no native review)",
                                      "files_sha256": {str(p.relative_to(out)).replace("\\", "/"): sha(p) for p in files if p.name != "MANIFEST_v2_1.json"}})
    print(f"wrote {len(files) + 1} files under {out}; repaired {len(changelog)} specs; heldout {len(HELDOUT)} specs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
