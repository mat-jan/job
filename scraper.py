import asyncio
import json
import re
from playwright.async_api import async_playwright
from urllib.parse import urljoin

# SŁOWA KLUCZOWE (Tylko te zawody nas interesują)
STRICT_KEYWORDS = ["kadr", "płac", "payroll", "hr", "kadrow", "płacow", "księgow", "biuro", "rekrutac"]
# WYKLUCZENIA (Odrzucamy śmieciowe wyniki)
EXCLUDE_KEYWORDS = ["kuchen", "fizycz", "kierowca", "nauczyciel", "sprząt", "produkcji", "magazyn", "budow", "kurier"]
# PRECYZYJNE WYKRYWANIE 3/4 ETATU
PART_TIME_PATTERN = r"(3/4|pół|0\.75|część|dodatkow|elastycz|wymiar)\s*(etatu|wymiar)?"

async def scrape_site(browser, name, url, selector, base_url=""):
    print(f"--- 🔎 Szukam na: {name} ---")
    # Tworzymy czysty kontekst z udawanym User-Agentem
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    
    try:
        # Zwiększony timeout i oczekiwanie na sieć
        await page.goto(url, wait_until="load", timeout=60000)
        await asyncio.sleep(5) # Czekamy na załadowanie ofert JS
        
        items = await page.query_selector_all(selector)
        results = []
        
        for item in items:
            try:
                # Wyciąganie tytułu
                title_el = await item.query_selector("h2, h3, h6, [data-automation='job-title'], .listing__title, [data-cy='ad-title']")
                if not title_el: continue
                
                title_raw = (await title_el.inner_text()).strip()
                title_lower = title_raw.lower()
                
                # Filtracja tytułów
                if not any(kw in title_lower for kw in STRICT_KEYWORDS): continue
                if any(ex in title_lower for ex in EXCLUDE_KEYWORDS): continue

                # Wyciąganie linku (obsługa różnych struktur)
                link_el = await item.query_selector("a")
                link = await link_el.get_attribute("href") if link_el else None
                if not link or "google" in link: continue
                
                full_url = urljoin(base_url, link)
                
                # Wyciąganie treści do analizy adresu i firmy
                full_text = (await item.inner_text())
                lines = [l.strip() for l in full_text.split('\n') if len(l.strip()) > 1]
                
                # Firma to zazwyczaj druga sensowna linia
                company = lines[1] if len(lines) > 1 else "Firma"
                
                # Szukamy lokalizacji w tekście
                location = "Otwock / Warszawa"
                for line in lines:
                    if any(x in line for x in ["Otwock", "Warszawa", "ul.", "Józefów", "Mokotów", "Ursynów", "Wawer"]):
                        if len(line) < 40 and "Praca" not in line:
                            location = line
                            break
                
                # Wykrywanie 3/4 etatu przez Regex
                is_part_time = bool(re.search(PART_TIME_PATTERN, full_text.lower()))

                print(f"   ✅ OK: {title_raw[:35]}... | {location}")

                results.append({
                    "title": title_raw.capitalize(),
                    "company": company,
                    "location": location,
                    "url": full_url,
                    "source": name,
                    "part_time": is_part_time
                })
            except: continue
        
        await context.close()
        return results
    except Exception as e:
        print(f"❌ BŁĄD {name}: {e}")
        await context.close()
        return []

async def main():
    async with async_playwright() as p:
        # Kluczowe dla GitHub Actions: headless=True
        browser = await p.chromium.launch(headless=True)
        
        sources = [
            ("Pracuj.pl", "https://www.pracuj.pl/praca/specjalista%20ds.%20kadr%20i%20p%C5%82ac;kw/otwock;wp?rd=20", "div[data-test='default-offer']", "https://www.pracuj.pl"),
            ("OLX", "https://www.olx.pl/praca/administracja-biurowa/otwock/?search%5Bdist%5D=30&q=kadry", "div[data-cy='l-card']", "https://www.olx.pl"),
            ("Praca.pl", "https://www.praca.pl/s-specjalista,ds,kadr,i,plac_m-otwock.html?p=Specjalista%20ds.%20Kadr%20i%20P%C5%82ac&m=Otwock", "li.listing__item", "https://www.praca.pl")
        ]
        
        # Równoległe pobieranie danych
        all_results = await asyncio.gather(*(scrape_site(browser, *s) for s in sources))
        
        # Łączenie i usuwanie duplikatów
        flat_results = [item for sublist in all_results for item in sublist]
        unique_results = list({j['url']: j for j in flat_results}.values())
        
        # Zapis do pliku JSON
        with open('oferty.json', 'w', encoding='utf-8') as f:
            json.dump(unique_results, f, ensure_ascii=False, indent=4)
            
        print(f"\n🚀 GOTOWE: Zebrano {len(unique_results)} ofert.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())