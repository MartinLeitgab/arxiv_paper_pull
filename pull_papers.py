# %%
import arxiv

def download_with_arxiv_package(arxiv_id, download_dir="./"):
    """Download using the official arxiv Python package"""
    # Search for the paper
    search = arxiv.Search(id_list=[arxiv_id])
    paper = next(search.results())
    
    # Download PDF
    filename = paper.download_pdf(dirpath=download_dir)
    print(f"Downloaded: {filename}")
    
    return paper  # Returns paper object with metadata

# Usage
paper = download_with_arxiv_package("2301.00001")
print(f"Title: {paper.title}")
print(f"Authors: {[author.name for author in paper.authors]}")
# %%
# %%

"""
Script to download the 100 most cited papers from arXiv's cs.AI category.

This script uses multiple approaches:
1. Semantic Scholar API to get citation counts
2. arXiv API to get cs.AI papers
3. Downloads PDFs based on citation ranking

Requirements:
pip install requests tqdm arxiv

Usage:
python download_top_cited_ai_papers.py
"""

import requests
import time
import json
import os
from tqdm import tqdm
from datetime import datetime, timedelta
import urllib.parse
import xml.etree.ElementTree as ET

class ArxivCitationDownloader:
    def __init__(self, max_papers=100):
        self.max_papers = max_papers
        self.semantic_scholar_base = "https://api.semanticscholar.org/graph/v1"
        self.arxiv_base = "http://export.arxiv.org/api/query"
        self.download_dir = "top_cited_cs_ai_papers"
        os.makedirs(self.download_dir, exist_ok=True)
        
        # Rate limiting
        self.request_delay = 1.0  # seconds between requests
        
    def get_arxiv_cs_ai_papers(self, max_results=2000):
        """Get recent cs.AI papers from arXiv API"""
        print("Fetching cs.AI papers from arXiv...")
        
        # Get papers from the last 3 years to have enough for citation analysis
        papers = []
        start_index = 0
        batch_size = 100
        
        while len(papers) < max_results:
            query_params = {
                'search_query': 'cat:cs.AI',
                'start': start_index,
                'max_results': batch_size,
                'sortBy': 'submittedDate',
                'sortOrder': 'descending'
            }
            
            query_string = urllib.parse.urlencode(query_params)
            print(f"start_index = {start_index}, len(papers) = {len(papers)}, fetching papers from arXiv with query: {query_string}")
            url = f"{self.arxiv_base}?{query_string}"
                            
            try:
                response = requests.get(url)
                response.raise_for_status()
                
                # Parse XML response
                root = ET.fromstring(response.content)
                entries = root.findall('{http://www.w3.org/2005/Atom}entry')
                
                if not entries:
                    print(f"   empty query return!")
                    break
                print(f"  fetched {len(entries)} entries from arXiv")
                for entry in entries:
                    arxiv_id = entry.find('{http://www.w3.org/2005/Atom}id').text.split('/')[-1]
                    title = entry.find('{http://www.w3.org/2005/Atom}title').text.strip()
                    
                    # Get authors
                    authors = []
                    for author in entry.findall('{http://www.w3.org/2005/Atom}author'):
                        name = author.find('{http://www.w3.org/2005/Atom}name').text
                        authors.append(name)
                    
                    # Get publication date
                    published = entry.find('{http://www.w3.org/2005/Atom}published').text[:10]
                    
                    papers.append({
                        'arxiv_id': arxiv_id,
                        'title': title,
                        'authors': authors,
                        'published': published,
                        'citations': 0  # Will be filled by Semantic Scholar
                    })
                
                start_index += batch_size
                time.sleep(self.request_delay)
                
            except Exception as e:
                print(f"Error fetching arXiv papers: {e}")
                break
        
        print(f"Retrieved {len(papers)} cs.AI papers from arXiv")
        return papers
    
    def get_semantic_scholar_citations(self, papers):
        """Get citation counts from Semantic Scholar API"""
        print("Getting citation counts from Semantic Scholar...")
        
        papers_with_citations = []
        
        for paper in tqdm(papers, desc="Fetching citations"):
            try:
                # Search for paper by title on Semantic Scholar
                search_url = f"{self.semantic_scholar_base}/paper/search"
                search_params = {
                    'query': paper['title'],
                    'fields': 'title,authors,citationCount,externalIds,year'
                }
                
                response = requests.get(search_url, params=search_params)
                response.raise_for_status()
                
                search_results = response.json()
                
                # Find matching paper (look for arXiv ID in externalIds)
                best_match = None
                for result in search_results.get('data', []):
                    external_ids = result.get('externalIds', {})
                    if external_ids and 'ArXiv' in external_ids:
                        arxiv_id_clean = paper['arxiv_id'].replace('v1', '').replace('v2', '').replace('v3', '')
                        if external_ids['ArXiv'] == arxiv_id_clean:
                            best_match = result
                            break
                
                # If no exact match, try title similarity
                if not best_match and search_results.get('data'):
                    best_match = search_results['data'][0]  # Take first result
                
                if best_match:
                    paper['citations'] = best_match.get('citationCount', 0)
                    paper['semantic_scholar_id'] = best_match.get('paperId', '')
                else:
                    paper['citations'] = 0
                
                papers_with_citations.append(paper)
                
                # Rate limiting
                time.sleep(self.request_delay)
                
            except Exception as e:
                print(f"Error getting citations for {paper['arxiv_id']}: {e}")
                paper['citations'] = 0
                papers_with_citations.append(paper)
                time.sleep(self.request_delay)
        
        return papers_with_citations
    
    def download_paper_pdf(self, arxiv_id, title, authors):
        """Download PDF from arXiv"""
        # Clean filename
        clean_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"{arxiv_id}_{clean_title[:50]}.pdf"
        filepath = os.path.join(self.download_dir, filename)
        
        # Skip if already downloaded
        if os.path.exists(filepath):
            return filepath
        
        # Download PDF
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        
        try:
            response = requests.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            return filepath
            
        except Exception as e:
            print(f"Error downloading {arxiv_id}: {e}")
            return None
    
    def save_metadata(self, papers, filename="top_cited_papers_metadata.json"):
        """Save paper metadata to JSON file"""
        filepath = os.path.join(self.download_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(papers, f, indent=2, ensure_ascii=False)
        print(f"Metadata saved to {filepath}")
    
    def run(self):
        """Main execution function"""
        print(f"Starting download of top {self.max_papers} cited cs.AI papers...")
        
        # Step 1: Get cs.AI papers from arXiv
        print("step 1 get paper list from arxiv")
        arxiv_papers = self.get_arxiv_cs_ai_papers(max_results=2000)
        return

        # Step 2: Get citation counts from Semantic Scholar
        print("step 2 get citations for all papers")
        papers_with_citations = self.get_semantic_scholar_citations(arxiv_papers)
        
        # Step 3: Sort by citation count and get top papers
        top_papers = sorted(papers_with_citations, 
                          key=lambda x: x['citations'], 
                          reverse=True)[:self.max_papers]
        
        print(f"\nTop {len(top_papers)} most cited cs.AI papers:")
        for i, paper in enumerate(top_papers[:10], 1):
            print(f"{i}. {paper['title']} - {paper['citations']} citations")
        
        # Step 4: Save metadata
        self.save_metadata(top_papers)
        
        # Step 5: Download PDFs
        print(f"\nDownloading PDFs...")
        successful_downloads = 0
        
        for paper in tqdm(top_papers, desc="Downloading PDFs"):
            filepath = self.download_paper_pdf(
                paper['arxiv_id'], 
                paper['title'], 
                paper['authors']
            )
            
            if filepath:
                successful_downloads += 1
            
            time.sleep(0.5)  # Be nice to arXiv servers
        
        print(f"\nDownload complete!")
        print(f"Successfully downloaded {successful_downloads}/{len(top_papers)} papers")
        print(f"Papers saved to: {self.download_dir}")
        
        return top_papers


if __name__ == "__main__":
    #print("Choose download method:")
    #print("1. Automatic citation-based ranking (using Semantic Scholar API)")
    #print("2. Download from curated list of highly cited papers")
    
    #choice = input("Enter choice (1 or 2): ").strip()
    
    #if choice == "1":
    downloader = ArxivCitationDownloader(max_papers=100)
    top_papers = downloader.run()
    #elif choice == "2":
    #    downloader = CuratedListDownloader()
    #    downloader.download_curated_papers()
    #else:
    #    print("Invalid choice. Using automatic method.")
    #    downloader = ArxivCitationDownloader(max_papers=100)
    #    top_papers = downloader.run()


    