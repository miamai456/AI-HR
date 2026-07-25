CREATE TABLE dim_candidate (
  candidate_id VARCHAR(32) PRIMARY KEY,
  region VARCHAR(32) NOT NULL,
  experience_years INT NOT NULL,
  education_level VARCHAR(32) NOT NULL,
  current_title VARCHAR(64) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE dim_job (
  job_id VARCHAR(32) PRIMARY KEY,
  job_category VARCHAR(32) NOT NULL,
  region VARCHAR(32) NOT NULL,
  seniority_level VARCHAR(32) NOT NULL,
  opened_at DATE NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE dim_recruiter (
  recruiter_id VARCHAR(32) PRIMARY KEY,
  recruiter_name VARCHAR(64) NOT NULL,
  region VARCHAR(32) NOT NULL,
  team VARCHAR(32) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE dim_model_version (
  model_version_id VARCHAR(32) PRIMARY KEY,
  model_version VARCHAR(32) NOT NULL UNIQUE,
  deployed_at DATE NOT NULL,
  description VARCHAR(128) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE fact_recommendation (
  recommendation_id VARCHAR(40) PRIMARY KEY,
  candidate_id VARCHAR(32) NOT NULL,
  job_id VARCHAR(32) NOT NULL,
  recruiter_id VARCHAR(32) NOT NULL,
  model_version_id VARCHAR(32) NOT NULL,
  source VARCHAR(16) NOT NULL,
  recommendation_score DOUBLE NOT NULL,
  recommended_at DATETIME NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_reco_candidate FOREIGN KEY (candidate_id) REFERENCES dim_candidate(candidate_id),
  CONSTRAINT fk_reco_job FOREIGN KEY (job_id) REFERENCES dim_job(job_id),
  CONSTRAINT fk_reco_recruiter FOREIGN KEY (recruiter_id) REFERENCES dim_recruiter(recruiter_id),
  CONSTRAINT fk_reco_model FOREIGN KEY (model_version_id) REFERENCES dim_model_version(model_version_id)
);

CREATE TABLE fact_funnel_event (
  event_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  recommendation_id VARCHAR(40) NOT NULL,
  stage VARCHAR(32) NOT NULL,
  status VARCHAR(16) NOT NULL,
  event_at DATETIME NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_funnel_event_recommendation_stage UNIQUE (recommendation_id, stage),
  CONSTRAINT fk_event_recommendation FOREIGN KEY (recommendation_id)
    REFERENCES fact_recommendation(recommendation_id)
);
