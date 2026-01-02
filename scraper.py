import asyncio
import json
from playwright.async_api import async_playwright
from urllib.parse import urljoin

# ŚCISŁY FILTR: Oferta musi zawierać przynajmniej jedno z tych słów w tytule
STRICT_KEYWORDS = ["kadr", "płac", "payroll", "hr", "kadrow", "płacow", "księgow"]
# WYKLUCZENIA: Jeśli te słowa są w tytule, odrzucamy (np. pomoc kuchenna, kierowca)
EXCLUDE_KEYWORDS = ["kuchen", "fizycz", "kierowca", "nauczyciel", "sprząt", "produkcji", "magazyn"]

PART_TIME_KEYWORDS = ["3/4", "część", "pół", "dodatkow", "zlecenie", "elastycz", "wymiar", "godzin"]

async def scrape_site(browser, name, url, selector, base_url=""):
    print(f"--- 🔎 Szukam na: {name} ---")
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(4) 
        
        items = await page.query_selector_all(selector)
        results = []
        
        for item in items:
            try:
                title_el = await item.query_selector("h2, h3, h6, [data-automation='job-title'], .listing__title")
                if not title_el: continue
                
                title = (await title_el.inner_text()).strip().lower()
                
                # 1. Sprawdzamy czy tytuł jest sensowny (Słowa kluczowe)
                if not any(kw in title for kw in STRICT_KEYWORDS):
                    continue
                
                # 2. Sprawdzamy czy to nie jest "śmieciowa" oferta (Wykluczenia)
                if any(ex in title for ex in EXCLUDE_KEYWORDS):
                    continue

                link_el = await item.query_selector("a")
                content_text = (await item.inner_text())
                lines = [line.strip() for line in content_text.split('\n') if len(line.strip()) > 1]
                
                company = lines[1] if len(lines) > 1 else "Firma"
                location = "Otwock / Warszawa"
                
                # Szukamy adresu w dostępnych liniach tekstu
                for line in lines:
                    if any(x in line for x in ["Otwock", "Warszawa", "ul.", "Józefów", "Karczew", "Wiązowna", "Mokotów", "Ursynów", "Wawer"]):
                        if "Praca" in line and len(line) < 20: continue # Omija proste napisy typu "Praca Warszawa"
                        location = line
                        break

                if link_el:
                    link = await link_el.get_attribute("href")
                    if not link or "google" in link: continue
                    
                    full_url = urljoin(base_url, link)
                    is_part_time = any(kw in content_text.lower() for kw in PART_TIME_KEYWORDS)
                    
                    print(f"   ✅ [{name}] {title[:35]}... | {location[:25]}")

                    results.append({
                        "title": title.capitalize(),
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
        browser = await p.chromium.launch(headless=True)
        
        sources = [
            ("Pracuj.pl", "https://www.pracuj.pl/praca/specjalista%20ds.%20kadr%20i%20p%C5%82ac;kw/otwock;wp?rd=20", "div[data-test='default-offer']", "https://www.pracuj.pl"),
            ("OLX", "https://www.olx.pl/praca/administracja-biurowa/otwock/?search%5Bdist%5D=30&q=kadry", "div[data-cy='l-card']", "https://www.olx.pl"),
            ("Praca.pl", "https://www.praca.pl/s-specjalista,ds,kadr,i,plac_m-otwock.html?p=Specjalista%20ds.%20Kadr%20i%20P%C5%82ac&m=Otwock", "li.listing__item", "https://www.praca.pl")
        ]
        
        all_results = await asyncio.gather(*(scrape_site(browser, *s) for s in sources))
        
        flat_results = [item for sublist in all_results for item in sublist]
        unique_results = list({j['url']: j for j in flat_results}.values())
        
        with open('oferty.json', 'w', encoding='utf-8') as f:
            json.dump(unique_results, f, ensure_ascii=False, indent=4)
            
        print(f"\n🚀 GOTOWE: Zebrano {len(unique_results)} czystych ofert bez śmieci.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())