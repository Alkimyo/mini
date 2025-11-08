import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple

class Database:
    def __init__(self, db_path: str = "bot_data.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        """Database connection yaratish"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Database jadvallarini yaratish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Foydalanuvchilar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Testlar jadvali (admin tomonidan kiritilgan to'g'ri javoblar)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tests (
                test_id INTEGER PRIMARY KEY,
                answers TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (created_by) REFERENCES users(user_id)
            )
        ''')
        
        # Foydalanuvchilar javoblari
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                test_id INTEGER NOT NULL,
                user_answer TEXT NOT NULL,
                correct_count INTEGER NOT NULL,
                total_count INTEGER NOT NULL,
                score REAL NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (test_id) REFERENCES tests(test_id),
                UNIQUE(user_id, test_id)
            )
        ''')
        
        # Majburiy kanallar
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                channel_name TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    # ============ USER OPERATIONS ============
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Yangi foydalanuvchi qo'shish yoki mavjudini yangilash"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
        
        conn.commit()
        conn.close()
    
    def get_all_users(self) -> List[int]:
        """Barcha foydalanuvchilar ID larini olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM users')
        users = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        return users
    
    # ============ TEST OPERATIONS ============
    
    def add_test(self, test_id: int, answers: str, created_by: int):
        """Yangi test qo'shish yoki mavjudini yangilash"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO tests (test_id, answers, created_by)
            VALUES (?, ?, ?)
        ''', (test_id, answers.lower(), created_by))
        
        conn.commit()
        conn.close()
    
    def get_test(self, test_id: int) -> Optional[str]:
        """Test javoblarini olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT answers FROM tests WHERE test_id = ?', (test_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result[0] if result else None
    
    def get_all_tests(self) -> List[int]:
        """Barcha test ID larini olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT test_id FROM tests ORDER BY test_id')
        tests = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        return tests
    
    # ============ USER ANSWER OPERATIONS ============
    
    def save_user_answer(self, user_id: int, test_id: int, user_answer: str, 
                        correct_count: int, total_count: int):
        """Foydalanuvchi javobini saqlash"""
        score = (correct_count / total_count * 100) if total_count > 0 else 0
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO user_answers 
                (user_id, test_id, user_answer, correct_count, total_count, score)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, test_id, user_answer, correct_count, total_count, score))
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False
    
    def has_user_submitted(self, user_id: int, test_id: int) -> bool:
        """Foydalanuvchi bu test uchun javob yuborgan yoki yo'qligini tekshirish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM user_answers 
            WHERE user_id = ? AND test_id = ?
        ''', (user_id, test_id))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count > 0
    
    def get_leaderboard(self, test_id: int, limit: int = 10) -> List[Dict]:
        """Ma'lum test uchun eng yaxshi natijalarni olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                ua.user_id,
                u.first_name,
                u.last_name,
                u.username,
                ua.correct_count,
                ua.total_count,
                ua.score,
                ua.submitted_at
            FROM user_answers ua
            JOIN users u ON ua.user_id = u.user_id
            WHERE ua.test_id = ?
            ORDER BY ua.score DESC, ua.submitted_at ASC
            LIMIT ?
        ''', (test_id, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'user_id': row[0],
                'first_name': row[1],
                'last_name': row[2],
                'username': row[3],
                'correct_count': row[4],
                'total_count': row[5],
                'score': row[6],
                'submitted_at': row[7]
            })
        
        conn.close()
        return results
    
    # ============ CHANNEL OPERATIONS ============
    
    def add_channel(self, channel_id: str, channel_name: str = None):
        """Majburiy kanal qo'shish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO channels (channel_id, channel_name)
            VALUES (?, ?)
        ''', (channel_id, channel_name))
        
        conn.commit()
        conn.close()
    
    def remove_channel(self, channel_id: str):
        """Kanalni o'chirish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM channels WHERE channel_id = ?', (channel_id,))
        
        conn.commit()
        conn.close()
    
    def get_all_channels(self) -> List[Tuple[str, str]]:
        """Barcha majburiy kanallarni olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT channel_id, channel_name FROM channels')
        channels = [(row[0], row[1]) for row in cursor.fetchall()]
        
        conn.close()
        return channels
