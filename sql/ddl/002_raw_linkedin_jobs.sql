CREATE TABLE raw_linkedin_job_postings (
  job_link TEXT,
  last_processed_time TEXT,
  got_summary TEXT,
  got_ner TEXT,
  is_being_worked TEXT,
  job_title TEXT,
  company TEXT,
  job_location TEXT,
  first_seen TEXT,
  search_city TEXT,
  search_country TEXT,
  search_position TEXT,
  job_level TEXT,
  job_type TEXT,
  aihr_imported_at TEXT
);

CREATE TABLE raw_job_skills (
  job_link TEXT,
  job_skills TEXT,
  aihr_imported_at TEXT
);
