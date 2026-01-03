import os
import shutil
import re
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

# Configuration
DATA_DIR = "data/raw"       # Look for PDFs inside the 'raw' subfolder
DB_PATH = "data/chroma"     # Save the database inside the 'chroma' subfolder

def ingest_data():
    # 1. Clean Slate (Critical for Versioning)
    # We wipe the DB so old "Issue 4" rules don't conflict with "Issue 5"
    if os.path.exists(DB_PATH):
        shutil.rmtree(DB_PATH)
        print(f"🧹 Cleared old database at '{DB_PATH}' (Starting fresh)")

    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        print(f"📂 Created '{DATA_DIR}'. Please create year folders inside (e.g. data/2024/)!")
        return

    all_docs = []
    total_files = 0

    # 2. Walk through ALL folders (2024, 2025, etc.)
    print(f"🔍 Scanning '{DATA_DIR}' for PDFs...")
    
    for root, dirs, files in os.walk(DATA_DIR):
        for filename in files:
            if filename.lower().endswith('.pdf'):
                total_files += 1
                file_path = os.path.join(root, filename)
                
                # --- AUTO-DETECT METADATA ---
                
                # A. Detect Year from Folder Name OR Filename
                # Look at the folder name first (e.g. "data/2024")
                folder_name = os.path.basename(root)
                if folder_name.isdigit() and len(folder_name) == 4:
                    year = folder_name
                else:
                    # Fallback: Look for year in filename (e.g. "2025_Sporting.pdf")
                    year_match = re.search(r"20\d{2}", filename)
                    year = year_match.group(0) if year_match else "General"

                # B. Detect Type (Sporting vs Technical)
                doc_type = "Regulatory"
                if "sporting" in filename.lower(): doc_type = "Sporting"
                elif "technical" in filename.lower(): doc_type = "Technical"
                elif "financial" in filename.lower(): doc_type = "Financial"

                print(f"   📄 Processing: {filename}")
                print(f"      → Year: {year} | Type: {doc_type}")

                try:
                    # Load & Split
                    loader = PyPDFLoader(file_path)
                    raw_docs = loader.load()
                    
                    text_splitter = RecursiveCharacterTextSplitter(
                        chunk_size=1000,
                        chunk_overlap=200,
                        separators=["\n\n", "\n", "ARTICLE", " ", ""]
                    )
                    
                    splits = text_splitter.split_documents(raw_docs)
                    
                    # Tag Metadata
                    for doc in splits:
                        doc.metadata["source_year"] = str(year)
                        doc.metadata["type"] = doc_type
                        doc.metadata["filename"] = filename
                        # Use filename as source so user sees "Issue 7" in the citation
                        doc.metadata["source"] = filename 
                    
                    all_docs.extend(splits)
                    print(f"      → Added {len(splits)} chunks.")
                    
                except Exception as e:
                    print(f"      ⚠️ Failed to load: {e}")

    # 3. Save to Vector Database
    if all_docs:
        print(f"\n💾 Saving {len(all_docs)} chunks to 'backend/{DB_PATH}'...")
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        
        Chroma.from_documents(
            documents=all_docs,
            embedding=embeddings,
            persist_directory=DB_PATH
        )
        print("✅ Knowledge Base Updated Successfully!")
        print("   (Restart your backend to load the new rules)")
    else:
        print("\n⚠️ No PDFs found! Organize them like: data/2024/Sporting.pdf")

if __name__ == "__main__":
    ingest_data()