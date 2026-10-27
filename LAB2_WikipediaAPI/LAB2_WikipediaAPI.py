# ==============================================================================
# KOMÓRKA 1: INSTALACJA PAKIETÓW I MODELU JĘZYKOWEGO
# ==============================================================================
print("1/5. Przygotowywanie środowiska...")
!pip install --quiet wikipedia-api spacy geopandas shapely
!python -m spacy download pl_core_news_sm --quiet

print("\n Środowisko Google Colab zostało skonfigurowane!")

# ==============================================================================
# KOMÓRKA 2: GŁÓWNY SKRYPT INTERAKTYWNY (CZYSTY POTOK ETL)
# ==============================================================================
import os
import requests
import zipfile
import wikipediaapi
import spacy
import pandas as pd
import geopandas as gpd
import shapely
import unicodedata
from collections import Counter
from google.colab import files

# Ładowanie polskiego modelu językowego z wyłączeniem zbędnych modułów
nlp = spacy.load("pl_core_news_sm", disable=["parser", "senter"])

# Funkcja pomocnicza usuwająca polskie znaki diakrytyczne dla nagłówków HTTP (ASCII)
def clean_ascii(text):
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')

# ------------------------------------------------------------------------------
# 1. KONFIGURACJA WEJŚCIOWA I BEZPIECZNY USER-AGENT
# ------------------------------------------------------------------------------
wojewodztwa = [
    "dolnośląskie", "kujawsko-pomorskie", "lubelskie", "lubuskie",
    "łódzkie", "małopolskie", "mazowieckie", "opolskie",
    "podkarpackie", "podlaskie", "pomorskie", "śląskie",
    "świętokrzyskie", "warmińsko-mazurskie", "wielkopolskie", "zachodniopomorskie"
]

print("\n" + "=" * 65, flush=True)
print("     LABORATORIUM GIS: WikipediaAPI", flush=True)
print("=" * 65, flush=True)

print("\nLista województw Polski:", flush=True)
for idx, w in enumerate(wojewodztwa, 1):
    print(f"  [{idx:2d}] Województwo {w.capitalize()}", flush=True)

woj_choice = input("\n[Krok 1] Wybierz numer województwa (1-16) lub wpisz jego nazwę: ").strip()

if woj_choice.isdigit() and 1 <= int(woj_choice) <= 16:
    selected_woj = wojewodztwa[int(woj_choice) - 1]
else:
    selected_woj = woj_choice.lower()

limit_str = input("\n[Krok 2] Podaj docelową liczbę artykułów do akceptacji [zalecane 10]: ").strip()
limit_artykulow = int(limit_str) if limit_str.isdigit() else 10

# Generator bezpiecznego ciągu User-Agent bez polskich znaków (zgodnie z normą ASCII dla HTTP)
ua_woj = clean_ascii(selected_woj)
USER_AGENT = f"GIS_AcademicLab_{ua_woj}/1.0 (jakis.student@wat.edu.pl)"

# ------------------------------------------------------------------------------
# 2. WYSZUKIWANIE KANDYDATÓW (MEDIAWIKI API Z TIMEOUTEM)
# ------------------------------------------------------------------------------
def pobierz_szeroka_liste_kandydatow(nazwa_woj):
    artykul_glowny = f"Województwo {nazwa_woj}"
    frazy_szukane = [
        f"województwo {nazwa_woj}",
        f"geografia województwa {nazwa_woj}",
        f"zabytki województwa {nazwa_woj}",
        f"podział administracyjny województwa {nazwa_woj}",
        f"powiaty w województwie {nazwa_woj}",
        f"miasta w województwie {nazwa_woj}",
        f"geografia fizyczna {nazwa_woj}"
    ]
    
    kandydaci = [artykul_glowny]
    headers = {"User-Agent": USER_AGENT}
    
    for fraza in frazy_szukane:
        search_url = "https://pl.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": fraza,
            "format": "json",
            "srlimit": 20
        }
        try:
            res = requests.get(search_url, params=params, headers=headers, timeout=10).json()
            titles = [item['title'] for item in res.get('query', {}).get('search', [])]
            for t in titles:
                if t not in kandydaci and not t.startswith("Kategoria:") and not t.startswith("Plik:"):
                    kandydaci.append(t)
        except Exception:
            pass
            
    return kandydaci

wiki = wikipediaapi.Wikipedia(
    user_agent=USER_AGENT,
    language="pl"
)

kandydaci = pobierz_szeroka_liste_kandydatow(selected_woj)

# ------------------------------------------------------------------------------
# 3. INTERAKTYWNA PĘTLA WYBORU ARTYKUŁÓW (HUMAN-IN-THE-LOOP)
# ------------------------------------------------------------------------------
akceptowane_artykuly = []
obiekty_stron = []
teksty_artykulow = {}

print("\n" + "=" * 65, flush=True)
print(f" ETAP 1: WERYFIKACJA ARTYKUŁÓW DLA WOJEWÓDZTWA {selected_woj.upper()}", flush=True)
print(f" Zbudowano listę {len(kandydaci)} kandydatów. Cel: Akceptacja {limit_artykulow} haseł.", flush=True)
print("=" * 65 + "\n", flush=True)

for idx, tytul in enumerate(kandydaci, 1):
    if len(akceptowane_artykuly) >= limit_artykulow:
        break
        
    page = wiki.page(tytul)
    if not page.exists() or len(page.text) < 300:
        continue
        
    snippet = page.summary[:200].replace("\n", " ") + "..."
    
    print("-" * 65, flush=True)
    print(f"Kandydat #{idx}: '{tytul}' (Długość: {len(page.text)} znaków)", flush=True)
    print(f"Fragment: {snippet}", flush=True)
    print(f"Postęp akceptacji: [{len(akceptowane_artykuly)}/{limit_artykulow}]", flush=True)
    
    wybor = input(" -> Czy akceptujesz ten artykuł do analizy? [t = tak / n = nie]: ").strip().lower()
    
    if wybor in ["t", "tak", "y"]:
        akceptowane_artykuly.append(tytul)
        obiekty_stron.append(page)
        teksty_artykulow[tytul] = page.text
        print(f"  [+] ZAAKCEPTOWANO ({len(akceptowane_artykuly)}/{limit_artykulow}): '{tytul}'\n", flush=True)
    else:
        print(f"  [-] ODRZUCONO: '{tytul}'\n", flush=True)

print("=" * 65, flush=True)
print(f" SUKCES! Wybrano komplet {len(akceptowane_artykuly)} artykułów:", flush=True)
for a in akceptowane_artykuly:
    print(f"   • {a}", flush=True)
print("=" * 65 + "\n", flush=True)

# ------------------------------------------------------------------------------
# 4. ZAPIS PLIKU POŚREDNIEGO (SUROWE TEKSTY Z WIKIPEDII)
# ------------------------------------------------------------------------------
raw_text_filename = f"teksty_zrodlowe_{selected_woj}.txt"

with open(raw_text_filename, "w", encoding="utf-8") as f:
    f.write("=================================================================\n")
    f.write(f"  PLIK POŚREDNI ETL: SUROWE TEKSTY POŻYSKANE Z WIKIPEDIA-API\n")
    f.write(f"  Województwo: {selected_woj.upper()}\n")
    f.write(f"  Liczba artykułów: {len(obiekty_stron)}\n")
    f.write("=================================================================\n\n")
    
    for p in obiekty_stron:
        f.write("#" * 65 + "\n")
        f.write(f"TYTUŁ HASŁA: {p.title}\n")
        f.write(f"URL: {p.fullurl}\n")
        f.write(f"DŁUGOŚĆ CAŁKOWITA: {len(p.text)} znaków\n")
        f.write("#" * 65 + "\n\n")
        f.write("--- PODSUMOWANIE (SUMMARY) ---\n")
        f.write(p.summary + "\n\n")
        f.write("--- PEŁNA TREŚĆ ARTYKUŁU (FULL TEXT) ---\n")
        f.write(p.text + "\n\n")

print(f" -> Wygenerowano plik pośredni z surową treścią artykułów: '{raw_text_filename}'", flush=True)

# ------------------------------------------------------------------------------
# 5. EKSTRAKCJA FRAZ I LEMATYZACJA W SPACY
# ------------------------------------------------------------------------------
print("\n2/5. Rozpoczynanie analizy NLP i lematyzacji...", flush=True)
tekst_zbiorczy = "\n".join(teksty_artykulow.values())

nlp.max_length = len(tekst_zbiorczy) + 100000
doc = nlp(tekst_zbiorczy)

wykryte_frazy = []
ETYKIETY_GEOG = ["placeName", "geogName", "LOC", "GPE", "orgName"]
STOP_WORDS_GIS = ["polska", "europa", "niemcy", "rzeczpospolita", "unia europejska"]

for ent in doc.ents:
    if ent.label_ in ETYKIETY_GEOG:
        mianownik = " ".join([t.lemma_ for t in ent if not t.is_punct]).strip().title()
        if len(mianownik) > 2 and not mianownik.isdigit() and mianownik.lower() not in STOP_WORDS_GIS:
            wykryte_frazy.append(mianownik)

zliczenia = Counter(wykryte_frazy)
top_frazy = [f for f, c in zliczenia.most_common(200)]

print(f"   Wyekstrahowano {len(zliczenia)} unikalnych potencjalnych toponimów.", flush=True)

# ------------------------------------------------------------------------------
# 6A. GEOKODOWANIE LEMATÓW ZE SPACY (PULL Z WIKIPEDIA API)
# ------------------------------------------------------------------------------
print("\n3/5. Pobieranie współrzędnych geograficznych dla lematów...", flush=True)

headers = {"User-Agent": USER_AGENT}
session = requests.Session()
session.headers.update(headers)

geokodowane_baza = {}

paczki_list = [top_frazy[i:i + 40] for i in range(0, len(top_frazy), 40)]
total_paczki = len(paczki_list)

for idx_p, paczka in enumerate(paczki_list, 1):
    print(f" -> Geokodowanie toponimów - paczka {idx_p}/{total_paczki}...", flush=True)
    params = {
        "action": "query",
        "titles": "|".join(paczka),
        "redirects": 1,
        "prop": "coordinates",
        "coprop": "primary",
        "format": "json"
    }
    try:
        res = session.get("https://pl.wikipedia.org/w/api.php", params=params, headers=headers, timeout=8).json()
        pages = res.get("query", {}).get("pages", {})
        for p_id, p_info in pages.items():
            if "coordinates" in p_info and p_id != "-1":
                coords = p_info["coordinates"][0]
                title = p_info["title"]
                lat, lon = coords["lat"], coords["lon"]
                if 48.9 <= lat <= 55.0 and 14.0 <= lon <= 24.5:
                    geokodowane_baza[title] = {"X": lon, "Y": lat}
    except Exception:
        pass

# ------------------------------------------------------------------------------
# 6B. KATEGORYZACJA SEMANTYCZNA I ZLICZANIE FREKWENCJI
# ------------------------------------------------------------------------------
def oznacz_typ_obiektu(tytul):
    t_low = tytul.lower()
    if any(w in t_low for w in ['rzeka', 'jezioro', 'kanał', 'zbiornik', 'potok', 'dopływ', 'staw', 'odra', 'nysa', 'wisła', 'warta']):
        return "Woda / Obiekt hydrograficzny"
    elif any(w in t_low for w in ['zamek', 'pałac', 'uniwersytet', 'kościół', 'muzeum', 'katedra', 'park', 'rezerwat', 'dwór', 'politechnika', 'twierdza']):
        return "Zabytek / Instytucja / Park"
    elif any(w in t_low for w in ['województwo', 'powiat', 'gmina', 'wyżyna', 'śląsk', 'kotlina', 'góry', 'pojezierze', 'beskidy', 'sudety']):
        return "Region / Jednostka terytorialna"
    else:
        return "Miejscowość / Osada"

tekst_lower = tekst_zbiorczy.lower()
wyniki_obiekty = []

for title, coords in geokodowane_baza.items():
    czysta_nazwa = title.split("(")[0].strip()
    rdzen = czysta_nazwa.lower()

    count = tekst_lower.count(rdzen)
    if count > 0:
        wyniki_obiekty.append({
            "nazwa_glowna": czysta_nazwa,
            "wojewodztwo_zrodlowe": selected_woj,
            "typ_obiektu": oznacz_typ_obiektu(title),
            "X": coords["X"],
            "Y": coords["Y"],
            "liczba_wzmianek": count
        })

# ------------------------------------------------------------------------------
# 7. PRZETWARZANIE PRZESTRZENNE W GEOPANDAS (REPROJEKCJA DO EPSG:2180)
# ------------------------------------------------------------------------------
df_geo = pd.DataFrame(wyniki_obiekty)

print("\n4/5. Tworzenie warstwy przestrzennej i transformacja do PL-1992...", flush=True)

if not df_geo.empty:
    gdf_prng = gpd.GeoDataFrame(
        df_geo,
        geometry=gpd.points_from_xy(df_geo.X, df_geo.Y),
        crs="EPSG:4326"
    )

    gdf_wynik_2180 = (
        gdf_prng.drop_duplicates(subset=["nazwa_glowna", "X", "Y"])
        .to_crs(epsg=2180)
        .sort_values(by="liczba_wzmianek", ascending=False)
    )
else:
    gdf_wynik_2180 = gpd.GeoDataFrame()

# ------------------------------------------------------------------------------
# 8. ZAPIS PLIKÓW I AUTOMATYCZNE PAKOWANIE ZIP
# ------------------------------------------------------------------------------
print(f"\n DIAGNOSTYKA: Pomyślnie zgeokodowano {len(gdf_wynik_2180)} obiektów na mapie!", flush=True)

if len(gdf_wynik_2180) > 0:
    base_name = f"toponimy_{selected_woj}"
    gpkg_filename = f"{base_name}.gpkg"
    report_filename = f"raport_{selected_woj}.txt"
    zip_filename = f"projekt_{selected_woj}.zip"

    # 1. Zapis warstwy GeoPackage
    gdf_wynik_2180.to_file(gpkg_filename, driver="GPKG", layer="toponimy_wiki")

    # 2. Zapis raportu podsumowującego
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write("=================================================================\n")
        f.write(f"      RAPORT LABORATORIUM OZDwG - WikipediaAPI\n")
        f.write("=================================================================\n")
        f.write(f"Województwo źródłowe: {selected_woj.upper()}\n")
        f.write(f"Liczba zaakceptowanych artykułów: {len(akceptowane_artykuly)}\n")
        f.write(f"Łączna liczba zgeokodowanych toponimów: {len(gdf_wynik_2180)}\n\n")
        f.write("Zaakceptowane artykuły źródłowe:\n")
        for a in akceptowane_artykuly:
            f.write(f"  • {a}\n")
        f.write("\n" + "=" * 65 + "\n")
        f.write(" PEŁNY WYKAZ WYKRYTYCH I ZGEOKODOWANYCH TOPONIMÓW:\n")
        f.write("=" * 65 + "\n\n")
        f.write(gdf_wynik_2180[['nazwa_glowna', 'typ_obiektu', 'liczba_wzmianek']].to_string(index=False))

    # 3. Pakowanie 3 plików (GeoPackage + Raport + Surowy tekst)
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(gpkg_filename)
        zipf.write(report_filename)
        zipf.write(raw_text_filename)

    print(f"\n5/5. SUKCES! Utworzono paczkę ZIP z 3 plikami ({len(gdf_wynik_2180)} punktów): '{zip_filename}'", flush=True)
    print(" Inicjowanie automatycznego pobierania...", flush=True)
    files.download(zip_filename)

else:
    print(" OSTRZEŻENIE: Brak zgeokodowanych obiektów dla wybranych artykułów.", flush=True)
