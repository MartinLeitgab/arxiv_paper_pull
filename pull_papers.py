
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
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


class ArxivCitationDownloader:
    def __init__(self, max_papers=1000):
        self.max_papers = max_papers
        self.semantic_scholar_base = "https://api.semanticscholar.org/graph/v1"
        self.arxiv_base = "http://export.arxiv.org/api/query"
        self.download_dir = "top_cited_cs_ai_papers"
        os.makedirs(self.download_dir, exist_ok=True)
        
        # Rate limiting
        self.request_delay = 4.0  # seconds between requests, per arxiv API guidelines
        
    def get_arxiv_cs_ai_papers(self, max_results=60000):
        """Get recent cs.AI papers from arXiv API"""
        print(f"Fetching {max_results} cs.AI papers from arXiv...")
        

        # Format dates for arXiv query
        end_date = datetime(2025, 7, 1) #datetime.now()
        start_date = datetime(2024, 1, 1) # knowledge cutoff GPT 4o Dec 2023
        #start_str = start_date.strftime('%Y%m%d')
        #end_str = end_date.strftime('%Y%m%d')
        #query = f'cat:cs.AI AND submittedDate:[{start_str}0000 TO {end_str}2359]'
        # Get papers from the last 3 years to have enough for citation analysis
        papers = []


        # due to api instability with pagination, keep returns to 400 per query, and use two week-based pagination
        current_start = start_date

        while current_start < end_date: # continue until have scanned all max available input paper

            if len(papers) >= max_results: # continue until have enough input papers
                break
            
            slice_end = min(current_start + timedelta(days=7), end_date)
            start_str = current_start.strftime('%Y%m%d')
            end_str = slice_end.strftime('%Y%m%d')
            print(f"\n new time slice, current_start = {current_start.strftime('%Y-%m-%d')}, end_date = {slice_end.strftime('%Y-%m-%d')}")
            
            query = f'cat:cs.AI AND submittedDate:[{start_str}0000 TO {end_str}2359]'

            start_index = 0
            batch_size = 400 # inherent issue in arxiv- beyond 400 results pagination for higher pages breaks down; need to keep timeslice close to 400 result returns
            is_lastbatchinquery = False

            while is_lastbatchinquery == False : # loop until reach end of current time slice query results

                query_params = {
                    'search_query': query, # better than 'cat:cs.AI',
                    'start': start_index,
                    'max_results': batch_size,
                    #'sortBy': 'submittedDate', # messes up pagination/batch size
                    #'sortOrder': 'descending'
                }
                
                query_string = urllib.parse.urlencode(query_params)
                print(f"start_index = {start_index}, len(papers) = {len(papers)}, fetching papers from arXiv with query: {query_string}")
                url = f"{self.arxiv_base}?{query_string}"
                print(f"  fetching from arXiv: {url}")                
                try:
                    response = requests.get(url)
                    response.raise_for_status()
                    
                    # Parse XML response
                    root = ET.fromstring(response.content)
                    
                    # Look for entries first
                    entries = root.findall('{http://www.w3.org/2005/Atom}entry')
                    
                    '''
                    # Not provided by arxiv: Check for arXiv API errors (returned as special entry elements)
                    error_entries = []
                    for entry in entries:
                        entry_id = entry.find('{http://www.w3.org/2005/Atom}id')
                        if entry_id is not None and 'arxiv.org/api/errors' in entry_id.text:
                            error_entries.append(entry)
                    
                    if error_entries:
                        print("arXiv API Error(s) found:")
                        for error_entry in error_entries:
                            title = error_entry.find('{http://www.w3.org/2005/Atom}title')
                            summary = error_entry.find('{http://www.w3.org/2005/Atom}summary')
                            entry_id = error_entry.find('{http://www.w3.org/2005/Atom}id')
                            
                            title_text = title.text if title is not None else "Unknown error"
                            summary_text = summary.text if summary is not None else "No description"
                            id_text = entry_id.text if entry_id is not None else "No ID"
                            
                            print(f"  Error: {title_text}")
                            print(f"  Description: {summary_text}")
                            print(f"  ID: {id_text}")
                        
                        # Decide whether to retry or abort based on error type
                        print(f"Waiting {self.request_delay} seconds before retrying...")
                        time.sleep(self.request_delay)
                        continue
                    '''
                    # Filter out error entries from the actual paper entries
                    paper_entries = [entry for entry in entries if not (
                        entry.find('{http://www.w3.org/2005/Atom}id') is not None and 
                        'arxiv.org/api/errors' in entry.find('{http://www.w3.org/2005/Atom}id').text
                    )]
                    
                    if len(paper_entries) < batch_size and len(paper_entries) > 0:
                        print(f"   Incomplete or last query return- Got {len(paper_entries)} paper entries, expected {batch_size}")
                        is_lastbatchinquery = True
                    elif len(paper_entries) == 0:
                        print("   No paper entries found!")
                        
                        # Print response for debugging
                        #lines = response.text.split('\n')
                        #print("First few lines of arxiv response:")
                        #for i, line in enumerate(lines[:10], 1):
                        #    print(f"{i:2d}: {line}")
                        
                        #print(f"Waiting for {self.request_delay} seconds before retrying...")
                        #time.sleep(self.request_delay)
                        print(f"Error fetching arXiv papers: empty response, need to debug")
                        exit()
                    
                    # process returned entries    
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
                    
                    start_index += len(entries) # better than batch_size, arxiv sometimes returns fewer hits than maxresult/page size
                    time.sleep(self.request_delay)
                    
                except Exception as e:
                    print(f"Error fetching arXiv papers: {e}")
                    break
            # End of time slice loop
            current_start = slice_end # reset for next time slice in time slice loop

        # End of overall time window loop (hope to have reached targeted paper number before reaching end point)
        print(f"Retrieved {len(papers)} cs.AI papers from arXiv")

        return papers
    
    def get_semantic_scholar_citations(self, papers): # may need to look for other citation tracking with higher rate limit, or apply for semantic scholar api key for higher limit
        """Get citation counts from Semantic Scholar API"""
        print("Getting citation counts from Semantic Scholar...")
        
        papers_with_citations = []
        
        for paper in tqdm(papers, desc="Fetching citations"):
             while True : #and len(papers_with_citations) < 2:  # Retry loop for each paper until do not receive rate error
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
                    print(f"DEBUG Found {paper['citations']} citations for {paper['arxiv_id']}: {paper['title']}")
                    papers_with_citations.append(paper)
                    break # Exit retry loop on success
                    # Rate limiting- instead do opportunistically only if get errors
                    #time.sleep(self.request_delay)
                    
                except requests.exceptions.HTTPError as e:
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", "1")) # keep frequent as IP-based and may open up soon
                        print(f"Rate limit hit for '{paper}'. Retrying after {retry_after} seconds...")
                        time.sleep(retry_after)
                    else:
                        print(f"HTTP error for '{paper}': {e}")
                        break  # If it's not a retryable error, break to avoid infinite loop
                    #print(f"Error getting citations for {paper['arxiv_id']}: {e}")
                    #if response.status_code == 429:
                    #    print("Rate limit exceeded (429). Full response:")
                    #    print("Status Code:", response.status_code)
                    #    print("Headers:", response.headers)
                    #    print("Body:", response.text)  # or response.content for bytes
                    #else:
                    #    print("HTTP error occurred:", err)
                    #paper['citations'] = 0
                    #papers_with_citations.append(paper)
                    #time.sleep(self.request_delay)
                except Exception as e:
                    print(f"Unexpected error for '{paper}': {e}")
                    break  # Handle other errors gracefully
    
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
    
    def save_papers_to_excel(self, papers, filename="arxiv_cs_ai_papers.xlsx"):
        """Save papers to Excel file using pandas"""
        # Create DataFrame
        df = pd.DataFrame(papers)
        
        # Save to Excel
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Papers', index=False)
            
            # Get the workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Papers']
            
            # Auto-adjust column widths
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                
                # Set column width (with some padding)
                adjusted_width = min(max_length + 2, 50)  # Cap at 50 characters
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        print(f"Saved {len(papers)} papers to {filename}")
        return filename



    def run(self):
        """Main execution function"""
        print(f"Starting download of top {self.max_papers} cited cs.AI papers...")
        
        # Step 1: Get cs.AI papers from arXiv
        print("step 1 get paper list from arxiv")
        arxiv_papers = self.get_arxiv_cs_ai_papers(max_results=10000)
        self.save_papers_to_excel(arxiv_papers) # save intermediate list for debug
        
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
            else:
                print(f"Failed to download {paper['arxiv_id']}: {paper['title']}, citations {paper['citations']}, maybe withdrawn")
            
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
    downloader = ArxivCitationDownloader(max_papers=10000)
    top_papers = downloader.run()
    #elif choice == "2":
    #    downloader = CuratedListDownloader()
    #    downloader.download_curated_papers()
    #else:
    #    print("Invalid choice. Using automatic method.")
    #    downloader = ArxivCitationDownloader(max_papers=100)
    #    top_papers = downloader.run()


    
# %%
