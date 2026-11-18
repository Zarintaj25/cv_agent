"""
CV Yoxlama Agentinin alətləri (tools).
Bunlar sadə Python funksiyalarıdır. Hansının nə vaxt çağırılacağına AGENT (LLM) özü qərar verir.
"""
import re

# ---------------------------------------------------------------
# Bacarıqlar lüğəti: kanonik ad -> mətndə axtarılacaq sözlər
# ---------------------------------------------------------------
SKILLS = {
    # Proqramlaşdırma
    "Python": ["python"],
    "Java": ["java"],
    "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript"],
    "C#": ["c#", "csharp"],
    "C++": ["c++"],
    "PHP": ["php"],
    "Go": ["golang"],
    "React": ["react", "react.js", "reactjs"],
    "Node.js": ["node.js", "nodejs", "node"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi"],
    ".NET": [".net", "dotnet", "asp.net"],
    "HTML/CSS": ["html", "css"],
    # Data
    "SQL": ["sql", "mysql", "postgresql", "postgres", "ms sql", "oracle"],
    "Excel": ["excel"],
    "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau"],
    "Pandas": ["pandas"],
    "Machine Learning": ["machine learning", "maşın öyrənməsi", "ml"],
    "Statistika": ["statistika", "statistics"],
    "Data analitika": ["data analitika", "data analysis", "data analytics", "məlumat təhlili"],
    # DevOps / alətlər
    "Git": ["git", "github", "gitlab"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "Linux": ["linux"],
    "REST API": ["rest api", "rest", "api"],
    # Biznes / dizayn
    "Figma": ["figma"],
    "Photoshop": ["photoshop"],
    "1C": ["1c"],
    "Mühasibat": ["mühasibat", "accounting"],
    "Satış": ["satış", "sales"],
    "Marketinq": ["marketinq", "marketing", "smm"],
    "Layihə idarəetməsi": ["layihə idarəetməsi", "project management", "scrum", "agile", "jira"],
    # Dillər
    "İngilis dili": ["ingilis dili", "english", "ingilis"],
    "Rus dili": ["rus dili", "russian", "rus"],
    "Türk dili": ["türk dili", "turkish"],
    # Soft skills
    "Komanda işi": ["komanda işi", "komandada iş", "teamwork", "team player"],
    "Ünsiyyət": ["ünsiyyət", "communication"],
    "Problem həlli": ["problem həlli", "problem solving"],
    "Liderlik": ["liderlik", "leadership"],
}

# Qərarda İSTİFADƏ OLUNMAMALI həssas sahələr (guardrail)
SENSITIVE_PATTERNS = [
    r"(?im)^\s*(yaş|age|doğum tarixi|təvəllüd|date of birth)\s*[:\-].*$",
    r"(?im)^\s*(cins|cinsi|gender|sex)\s*[:\-].*$",
    r"(?im)^\s*(milliyyət|milliyyəti|vətəndaşlıq|nationality|citizenship)\s*[:\-].*$",
    r"(?im)^\s*(ailə vəziyyəti|marital status|din|religion)\s*[:\-].*$",
]


def _remove_sensitive(text: str):
    """Yaş, cins, milliyyət və s. sətirlərini mətndən silir ki, bal onlara təsir etməsin."""
    removed = 0
    for p in SENSITIVE_PATTERNS:
        text, n = re.subn(p, "", text)
        removed += n
    return text, removed


def _find_skills(text: str):
    low = " " + text.lower() + " "
    found = []
    for canon, words in SKILLS.items():
        for w in words:
            # söz sərhədi ilə axtarış (məs. "java" "javascript"-in içində tapılmasın)
            pattern = r"(?<![\w#+.])" + re.escape(w) + r"(?![\w#+])"
            if re.search(pattern, low):
                found.append(canon)
                break
    return found


def _years_of_experience(text: str):
    """'3 il təcrübə', '5+ years' kimi ifadələrdən ən böyük rəqəmi götürür."""
    nums = re.findall(r"(\d{1,2})\s*\+?\s*(?:il|ildən|years?|yrs?)", text.lower())
    return max((int(n) for n in nums), default=None)


# ===============================================================
# ALƏT 1: extract_skills
# ===============================================================
def extract_skills(text: str) -> dict:
    """Mətndən (CV və ya vakansiya) bacarıqları və təcrübə ilini çıxarır."""
    clean, _ = _remove_sensitive(text)
    skills = _find_skills(clean)
    return {
        "skills": skills,
        "skill_count": len(skills),
        "years_experience": _years_of_experience(clean),
    }


# ===============================================================
# ALƏT 2: score_match
# ===============================================================
def score_match(cv: str, vacancy: str) -> dict:
    """CV ilə vakansiyanı müqayisə edib 0-100 uyğunluq balı və əsaslandırma qaytarır.
    Bal = 80% bacarıq uyğunluğu + 20% təcrübə uyğunluğu.
    Yaş/cins/milliyyət sətirləri əvvəlcədən silinir və bala təsir etmir."""
    cv_clean, removed = _remove_sensitive(cv)
    vac_clean, _ = _remove_sensitive(vacancy)

    cv_skills = set(_find_skills(cv_clean))
    vac_skills = _find_skills(vac_clean)

    if not vac_skills:
        return {"error": "Vakansiya mətnində tanınan bacarıq tapılmadı. "
                         "İstifadəçidən tələbləri daha aydın yazmasını xahiş et."}

    matched = [s for s in vac_skills if s in cv_skills]
    missing = [s for s in vac_skills if s not in cv_skills]
    extra = sorted(cv_skills - set(vac_skills))
    skill_score = len(matched) / len(vac_skills) * 80

    cv_years = _years_of_experience(cv_clean)
    req_years = _years_of_experience(vac_clean)
    if req_years is None:
        exp_score, exp_note = 20, "Vakansiyada təcrübə tələbi göstərilməyib."
    elif cv_years is None:
        exp_score, exp_note = 0, f"Vakansiya {req_years} il tələb edir, CV-də təcrübə ili göstərilməyib."
    else:
        exp_score = min(cv_years / req_years, 1) * 20
        exp_note = f"Tələb: {req_years} il, namizəd: {cv_years} il."

    score = round(skill_score + exp_score)
    level = "Yüksək" if score >= 75 else "Orta" if score >= 50 else "Aşağı"

    return {
        "score": score,
        "level": level,
        "matched_skills": matched,
        "missing_skills": missing,
        "extra_skills": extra,
        "experience_note": exp_note,
        "sensitive_lines_ignored": removed,
        "note": "Bu bal yalnız tövsiyədir; yaş, cins və milliyyət nəzərə alınmayıb.",
    }


# ===============================================================
# ALƏT 3 (BONUS): rank_cvs
# ===============================================================
def rank_cvs(cvs: list, vacancy: str) -> dict:
    """Bir neçə CV-ni eyni vakansiyaya görə sıralayır.
    cvs: [{"name": "Namizəd 1", "text": "..."}, ...]"""
    results = []
    for i, c in enumerate(cvs, 1):
        r = score_match(c.get("text", ""), vacancy)
        if "error" in r:
            return r
        results.append({
            "name": c.get("name") or f"Namizəd {i}",
            "score": r["score"],
            "level": r["level"],
            "missing_skills": r["missing_skills"],
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    for pos, r in enumerate(results, 1):
        r["rank"] = pos
    return {"ranking": results,
            "note": "Sıralama yalnız tövsiyədir; son qərarı insan verməlidir."}


# ---------------------------------------------------------------
# LLM-ə göstərilən alət təsvirləri (OpenAI tool formatı)
# ---------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "extract_skills",
            "description": "Verilmiş mətndən (CV və ya vakansiya) bacarıqları və təcrübə ilini çıxarır. "
                           "İstifadəçi yalnız bacarıqların siyahısını istəyəndə istifadə et.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "CV və ya vakansiya mətni"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "score_match",
            "description": "Bir CV-ni bir vakansiya ilə müqayisə edib 0-100 uyğunluq balı, uyğun və çatışmayan "
                           "bacarıqları qaytarır. Həm CV, həm vakansiya mətni məlum olanda çağır.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cv": {"type": "string", "description": "Namizədin CV mətni (tam)"},
                    "vacancy": {"type": "string", "description": "Vakansiya tələbləri mətni (tam)"},
                },
                "required": ["cv", "vacancy"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rank_cvs",
            "description": "İki və ya daha çox CV-ni eyni vakansiyaya görə baldan asılı olaraq sıralayır.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cvs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["name", "text"],
                        },
                    },
                    "vacancy": {"type": "string"},
                },
                "required": ["cvs", "vacancy"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "extract_skills": extract_skills,
    "score_match": score_match,
    "rank_cvs": rank_cvs,
}
