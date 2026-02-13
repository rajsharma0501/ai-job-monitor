#!/usr/bin/env python3
"""
AI Job Monitor v2.0 - Intelligent role-based job tracking with freshness detection
Repository: https://github.com/YOUR_USERNAME/ai-job-monitor
Features: Smart scoring, state expiration, URL-based dedup, multi-channel alerts
License: MIT
"""

import requests
from bs4 import BeautifulSoup
import json
import hashlib
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, time as dt_time
import time
import os
from pathlib import Path
from collections import defaultdict
import sys

class JobMonitor:
    def __init__(self, config_file='config.template.json'):
        """Initialize monitor with config from file + environment variables"""
        # Load base config
        with open(config_file, 'r') as f:
            self.config = json.load(f)
        
        self.state_file = Path('job_state.json')
        
        # Configuration
        self.state_expiry_days = self.config.get('state_expiry_days', 90)
        self.max_job_age_days = self.config.get('max_job_age_days', 2)

        # Override with environment variables (GitHub Secrets)
        if os.getenv('TELEGRAM_BOT_TOKEN'):
            self.config['telegram']['enabled'] = True
            self.config['telegram']['bot_token'] = os.getenv('TELEGRAM_BOT_TOKEN')
            self.config['telegram']['chat_id'] = os.getenv('TELEGRAM_CHAT_ID')
            print("✓ Telegram configured from environment")
        else:
            print("ℹ Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")
        
        if os.getenv('EMAIL_PASSWORD'):
            self.config['email']['enabled'] = True
            self.config['email']['password'] = os.getenv('EMAIL_PASSWORD')
            if os.getenv('EMAIL_FROM'):
                self.config['email']['from'] = os.getenv('EMAIL_FROM')
                self.config['email']['to'] = os.getenv('EMAIL_FROM')
            print("✓ Email configured from environment")
        
        self.state = self.load_state()
        self.daily_digest = []
        
    def load_state(self):
        """Load previous job IDs with auto-expiration of old entries"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)

                cleaned_state = self.clean_old_state(state)
                old_count = sum(len(v) if isinstance(v, (list, dict)) else 0 for v in state.values())
                new_count = sum(len(v) if isinstance(v, (list, dict)) else 0 for v in cleaned_state.values())
                if old_count > new_count:
                    print(f"ℹ Cleaned {old_count - new_count} expired state entries (>{self.state_expiry_days} days old)")

                return cleaned_state
            except Exception as e:
                print(f"⚠ Warning: Could not load state: {e}")
                return {}
        return {}

    def clean_old_state(self, state):
        """Remove entries older than state_expiry_days"""
        cutoff = datetime.now() - timedelta(days=self.state_expiry_days)
        cleaned = {}
        
        for company, entries in state.items():
            if isinstance(entries, list):
                cleaned[company] = entries
            elif isinstance(entries, dict):
                valid_entries = {}
                for job_id, metadata in entries.items():
                    try:
                        first_seen_str = metadata.get('first_seen', '')
                        if first_seen_str:
                            first_seen = datetime.fromisoformat(first_seen_str)
                            if first_seen > cutoff:
                                valid_entries[job_id] = metadata
                        else:
                            valid_entries[job_id] = metadata
                    except Exception:
                        valid_entries[job_id] = metadata

                if valid_entries:
                    cleaned[company] = valid_entries
        
        return cleaned
    
    def save_state(self):
        """Save current job IDs with metadata"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"⚠ Warning: Could not save state: {e}")
    
    def calculate_job_score(self, job_title, company_priority='medium'):
        """
        Score job relevance from 0-100
        80+ = URGENT (instant Telegram)
        60-79 = HIGH (daily digest, highlighted)
        40-59 = MEDIUM (daily digest)
        <40 = LOW (weekly summary only)
        """
        score = 0
        title_lower = job_title.lower()
        
        # SENIORITY (30 points max)
        if 'principal' in title_lower:
            score += 30
        elif 'staff' in title_lower or 'senior staff' in title_lower:
            score += 28
        elif 'lead' in title_lower:
            score += 20
        elif 'senior' in title_lower:
            score += 15
        
        # DOMAIN FIT (40 points max)
        domain_keywords = {
            'agent': 25,
            'llm': 20,
            'reinforcement learning': 20,
            'rl engineer': 20,
            'mlops': 15,
            'ml platform': 18,
            'ai platform': 18,
            'data platform': 15,
            'machine learning infrastructure': 18,
            'ml infrastructure': 18,
            'ai infrastructure': 18,
            'copilot': 20,
            'generative ai': 15,
            'foundation model': 18,
            'model training': 12,
            'distributed systems': 10,
            'compiler': 15,
        }
        
        domain_score = 0
        for keyword, points in domain_keywords.items():
            if keyword in title_lower:
                domain_score = max(domain_score, points)
        score += domain_score
        
        # ROLE TYPE (20 points max)
        if 'engineer' in title_lower:
            score += 20
        elif 'scientist' in title_lower:
            score += 18
        elif 'architect' in title_lower:
            score += 15
        elif 'researcher' in title_lower:
            score += 12
        
        # LOCATION BONUS (10 points max)
        if 'hyderabad' in title_lower or 'chennai' in title_lower:
            score += 10
        elif 'remote' in title_lower or 'india' in title_lower:
            score += 5
        elif 'bengaluru' in title_lower or 'bangalore' in title_lower:
            score += 7
        
        # Company brand (minor adjustment, max ±5)
        if company_priority == 'high':
            score += 5
        
        return min(score, 100)
    
    def get_priority_level(self, score):
        """Convert score to priority tier"""
        if score >= 80:
            return 'URGENT'
        elif score >= 60:
            return 'HIGH'
        elif score >= 40:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def fetch_page(self, url):
        """Fetch page content with proper headers and error handling"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        }
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"  ⚠ Error fetching: {e}")
            return None
    
    def extract_jobs(self, company, url, html):
        """Extract job listings from HTML using BeautifulSoup"""
        if not html:
            return []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            jobs = []
            
            # Generic job extraction
            job_elements = soup.find_all(['a', 'div', 'li'], 
                                         class_=lambda x: x and any(kw in str(x).lower() 
                                         for kw in ['job', 'position', 'role', 'career', 'opening']))
            
            for elem in job_elements[:50]:
                title_elem = elem.find(['h2', 'h3', 'h4', 'span', 'a'])
                if not title_elem:
                    title_elem = elem
                
                title = title_elem.get_text(strip=True)
                
                # Skip if title is too short or too long
                if len(title) < 10 or len(title) > 200:
                    continue
                
                link = elem.get('href') if elem.name == 'a' else None
                if not link:
                    link_elem = elem.find('a')
                    if link_elem:
                        link = link_elem.get('href')
                
                if self.matches_criteria(title):
                    if self.is_job_too_old(elem.get_text(" ", strip=True)):
                        continue
                    if link and not link.startswith('http'):
                        from urllib.parse import urljoin
                        link = urljoin(url, link)
                    
                    # IMPROVED: Include URL in hash for better dedup
                    job_id = hashlib.md5(f"{company}:{title}:{link}".encode()).hexdigest()
                    
                    jobs.append({
                        'id': job_id,
                        'company': company,
                        'title': title,
                        'url': link or url,
                        'found_at': datetime.now().isoformat()
                    })
            
            return jobs
        except Exception as e:
            print(f"  ⚠ Error extracting jobs: {e}")
            return []

    def is_job_too_old(self, text):
        """Return True if posting looks older than max_job_age_days"""
        if not self.max_job_age_days:
            return False

        match = re.search(r"(\d+)\s+day", text.lower())
        if not match:
            return False

        try:
            days = int(match.group(1))
        except ValueError:
            return False

        return days > self.max_job_age_days
    
    def matches_criteria(self, title):
        """Basic filter - must be senior + technical role"""
        title_lower = title.lower()
        
        seniority_keywords = ['principal', 'staff', 'senior staff', 'lead', 'senior']
        has_seniority = any(kw in title_lower for kw in seniority_keywords)

        ai_keywords = ['ai', 'machine learning', 'ml', 'data', 'platform', 
                       'mlops', 'llm', 'agent', 'deep learning']
        has_ai = any(kw in title_lower for kw in ai_keywords)

        role_keywords = ['engineer', 'scientist', 'architect', 'researcher']
        has_role = any(kw in title_lower for kw in role_keywords)
        
        return has_seniority and (has_ai or has_role)
    
    def send_telegram_urgent(self, job, score):
        """Send URGENT alert via Telegram for high-scoring jobs"""
        if not self.config.get('telegram', {}).get('enabled'):
            return
        
        tg = self.config['telegram']
        
        priority_emoji = "🔥" if score >= 90 else "🚨"
        
        msg = (
            f"{priority_emoji} <b>URGENT JOB MATCH</b> {priority_emoji}\n"
            f"Score: {score}/100\n\n"
            f"🏢 <b>{job['company']}</b>\n"
            f"📋 <b>{job['title']}</b>\n\n"
            f"🔗 <a href=\"{job['url']}\">Apply Now</a>\n\n"
            f"⏰ {datetime.now().strftime('%I:%M %p IST')}\n"
            f"💡 Tip: Apply within 2 hours for best chance!"
        )
        
        api_url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
        
        try:
            response = requests.post(api_url, json={
                'chat_id': tg['chat_id'],
                'text': msg,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }, timeout=10)
            response.raise_for_status()
            print(f"  📱 Telegram alert sent (score: {score})")
        except requests.RequestException as e:
            print(f"  ⚠ Telegram failed: {e}")
    
    def send_daily_digest(self, jobs):
        """Send consolidated daily email digest"""
        if not jobs or not self.config.get('email', {}).get('enabled'):
            return
        
        email_cfg = self.config['email']
        
        by_priority = defaultdict(list)
        for job in jobs:
            by_priority[job['priority']].append(job)
        
        subject = f"📊 Daily Job Digest: {len(jobs)} New Roles"
        
        body_parts = [
            f"Job Digest for {datetime.now().strftime('%Y-%m-%d')}\n",
            f"Total: {len(jobs)} new principal/staff AI roles\n\n",
            "="*70 + "\n\n"
        ]
        
        for priority in ['HIGH', 'MEDIUM', 'LOW']:
            priority_jobs = by_priority.get(priority, [])
            if not priority_jobs:
                continue
            
            emoji = "🔴" if priority == 'HIGH' else "🟡" if priority == 'MEDIUM' else "⚪"
            body_parts.append(f"{emoji} {priority} PRIORITY ({len(priority_jobs)} roles)\n")
            body_parts.append("-"*70 + "\n\n")
            
            for job in sorted(priority_jobs, key=lambda x: x['score'], reverse=True):
                body_parts.append(f"🏢 {job['company']}")
                body_parts.append(f"📋 {job['title']}")
                body_parts.append(f"⭐ Match Score: {job['score']}/100")
                body_parts.append(f"🔗 {job['url']}\n\n")
            
            body_parts.append("\n")
        
        body = "\n".join(body_parts)
        
        try:
            msg = MIMEMultipart()
            msg['From'] = email_cfg['from']
            msg['To'] = email_cfg['to']
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(email_cfg['smtp_host'], email_cfg['smtp_port']) as server:
                server.starttls()
                server.login(email_cfg['from'], email_cfg['password'])
                server.send_message(msg)
            
            print(f"\n📧 Daily digest sent: {len(jobs)} jobs")
        except Exception as e:
            print(f"⚠ Email failed: {e}")
    
    def check_company(self, company_data):
        """Check one company with intelligent scoring and freshness tracking"""
        company = company_data['name']
        url = company_data['url']
        company_priority = company_data.get('priority', 'medium')
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking {company}...")
        
        html = self.fetch_page(url)
        jobs = self.extract_jobs(company, url, html)
        
        # Get current state (migrate old format to new if needed)
        company_state = self.state.get(company, {})
        if isinstance(company_state, list):
            print(f"  ℹ Migrating {company} state to new format")
            company_state = {
                job_id: {
                    'first_seen': datetime.now().isoformat(),
                    'last_seen': datetime.now().isoformat(),
                    'title': 'Unknown'
                }
                for job_id in company_state
            }

        # Find NEW jobs
        new_jobs = []
        for job in jobs:
            job_id = job['id']
            if job_id not in company_state:
                new_jobs.append(job)
                # Mark as seen with metadata
                company_state[job_id] = {
                    'first_seen': job['found_at'],
                    'last_seen': job['found_at'],
                    'title': job['title']
                }
            else:
                # Update last_seen for existing jobs (still active)
                company_state[job_id]['last_seen'] = datetime.now().isoformat()
        
        if new_jobs:
            print(f"  ✨ Found {len(new_jobs)} new job(s)")
            
            for job in new_jobs:
                # Calculate intelligent score
                score = self.calculate_job_score(job['title'], company_priority)
                priority = self.get_priority_level(score)
                
                job['score'] = score
                job['priority'] = priority
                
                print(f"     - [{score}/100 {priority}] {job['title']}")
                
                # INSTANT alert for URGENT (80+)
                if priority == 'URGENT':
                    self.send_telegram_urgent(job, score)
                # Add others to digest
                else:
                    self.daily_digest.append(job)
            
            # Update state
            self.state[company] = company_state
            self.save_state()
        else:
            print(f"  ✓ No new jobs")
        
        return new_jobs
    
    def should_send_digest(self):
        """Check if it's time for daily digest (9 AM IST)"""
        now = datetime.now()
        digest_time = dt_time(9, 0)

        return (digest_time <= now.time() <= dt_time(9, 30) and
                len(self.daily_digest) > 0)
    
    def run_once(self):
        """Run one complete check cycle"""
        print(f"\n{'='*60}")
        print(f"AI Job Monitor v2.0 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
        print(f"State expiry: {self.state_expiry_days} days")
        print(f"{'='*60}\n")

        all_new_jobs = []
        urgent_count = 0

        for company_data in self.config['companies']:
            try:
                new_jobs = self.check_company(company_data)
                all_new_jobs.extend(new_jobs)
                urgent_count += sum(1 for j in new_jobs if j.get('score', 0) >= 80)
                time.sleep(2)
            except Exception as e:
                print(f"  ❌ Error checking {company_data['name']}: {e}")

        if self.should_send_digest():
            self.send_daily_digest(self.daily_digest)
            self.daily_digest = []
        
        print(f"\n{'='*60}")
        print(f"Summary:")
        print(f"  Total new jobs: {len(all_new_jobs)}")
        print(f"  🔥 URGENT (Telegram sent): {urgent_count}")
        print(f"  📊 In digest queue: {len(self.daily_digest)}")
        print(f"{'='*60}\n")
        
        return all_new_jobs
    
    def run_continuous(self, interval_minutes=30):
        """Run continuously with specified check interval"""
        print(f"🚀 Starting continuous monitoring (every {interval_minutes} min)")
        print(f"📱 Telegram alerts: URGENT jobs (score 80+)")
        print(f"📧 Daily digest: 9 AM IST for others")
        print(f"🔄 State expiry: {self.state_expiry_days} days")
        print(f"Monitoring {len(self.config['companies'])} companies")
        print(f"Press Ctrl+C to stop\n")
        
        while True:
            try:
                self.run_once()
                print(f"⏳ Next check in {interval_minutes} minutes...")
                time.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                print("\n\n👋 Stopping monitor. Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Unexpected error: {e}")
                print(f"Retrying in {interval_minutes} minutes...")
                time.sleep(interval_minutes * 60)


def main():
    """Main entry point with CLI argument parsing"""
    monitor = JobMonitor()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        # Run once and exit (for GitHub Actions)
        monitor.run_once()
    else:
        # Run continuously (for local/VM)
        interval = int(sys.argv[1]) if len(sys.argv) > 1 else 30
        monitor.run_continuous(interval)


if __name__ == '__main__':
    main()

