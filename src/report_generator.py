"""
Enhanced Report Generator
Generates comprehensive upgrade reports with statistics and insights
"""

import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class FileUpgradeResult:
    """Result of upgrading a single file (redefined for report module)"""
    file_path: str
    success: bool
    attempts: int
    api_changes: List[str]
    error: Optional[str] = None
    diff: Optional[str] = None


class ReportGenerator:
    """
    Generate detailed upgrade reports with statistics and insights
    """
    
    def __init__(self):
        self.results: List[FileUpgradeResult] = []
        self.dependency_changes: List[str] = []
        self.start_time = datetime.now()
        self.total_cost_usd = 0.0
        self.total_tokens = 0
    
    def add_file_result(self, result: FileUpgradeResult):
        """Add a file upgrade result"""
        self.results.append(result)
    
    def add_dependency_changes(self, changes: List[str]):
        """Add dependency update changes"""
        self.dependency_changes.extend(changes)
    
    def set_cost_info(self, total_cost: float, total_tokens: int):
        """Set cost tracking information"""
        self.total_cost_usd = total_cost
        self.total_tokens = total_tokens
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"
    
    def _get_file_stats(self) -> Dict[str, Any]:
        """Calculate file statistics"""
        successful = [r for r in self.results if r.success]
        failed = [r for r in self.results if not r.success]
        
        total_attempts = sum(r.attempts for r in self.results)
        avg_attempts = total_attempts / len(self.results) if self.results else 0
        
        # API change frequency
        all_changes = []
        for result in successful:
            all_changes.extend(result.api_changes)
        
        change_counts = {}
        for change in all_changes:
            change_counts[change] = change_counts.get(change, 0) + 1
        
        return {
            "total": len(self.results),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": len(successful) / len(self.results) * 100 if self.results else 0,
            "total_attempts": total_attempts,
            "avg_attempts": avg_attempts,
            "change_counts": change_counts
        }
    
    def generate_report(self, output_path: str) -> None:
        """
        Generate comprehensive markdown upgrade report
        
        Args:
            output_path: Path to save the report
        """
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        stats = self._get_file_stats()
        successful = [r for r in self.results if r.success]
        failed = [r for r in self.results if not r.success]
        
        # Build report
        report = self._build_report_header(end_time, duration, stats)
        report += self._build_executive_summary(stats, duration)
        report += self._build_dependency_section()
        report += self._build_cost_section(duration)
        report += self._build_successful_upgrades_section(successful)
        report += self._build_failed_upgrades_section(failed)
        report += self._build_statistics_section(stats)
        report += self._build_recommendations_section(successful, failed)
        
        # Write report
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(report)
        
        print(f"\n📊 Report generated: {output_path}")
    
    def _build_report_header(self, end_time: datetime, duration: float, stats: Dict) -> str:
        """Build report header section"""
        return f"""# 🚀 ML Repository Upgrade Report

**Generated:** {end_time.strftime('%Y-%m-%d %H:%M:%S')}  
**Duration:** {self._format_duration(duration)}  
**Total Files:** {stats['total']}  
**Successful:** {stats['successful']} ({stats['success_rate']:.1f}%)  
**Failed:** {stats['failed']}  

---

"""
    
    def _build_executive_summary(self, stats: Dict, duration: float) -> str:
        """Build executive summary section"""
        success_emoji = "✅" if stats['success_rate'] > 80 else "⚠️" if stats['success_rate'] > 50 else "❌"
        
        report = f"""## 📋 Executive Summary

{success_emoji} **{stats['successful']}/{stats['total']}** files upgraded successfully (**{stats['success_rate']:.1f}%**)

### Key Metrics
- **Processing Rate:** {stats['total'] / duration:.2f} files/second
- **Average Attempts:** {stats['avg_attempts']:.1f} per file
- **Total LLM Calls:** {stats['total_attempts']}

"""
        return report
    
    def _build_dependency_section(self) -> str:
        """Build dependency updates section"""
        if not self.dependency_changes:
            return ""
        
        report = """## 📦 Dependency Updates

The following ML/AI library versions were updated:

"""
        for change in self.dependency_changes:
            report += f"- {change}\n"
        
        report += "\n"
        return report
    
    def _build_cost_section(self, duration: float) -> str:
        """Build cost and resource usage section"""
        if self.total_cost_usd == 0:
            return ""
        
        cost_per_file = self.total_cost_usd / len(self.results) if self.results else 0
        tokens_per_file = self.total_tokens / len(self.results) if self.results else 0
        
        return f"""## 💰 Cost Analysis

- **Total Cost:** ${self.total_cost_usd:.4f}
- **Total Tokens:** {self.total_tokens:,}
- **Cost per File:** ${cost_per_file:.4f}
- **Tokens per File:** {tokens_per_file:,.0f}
- **Processing Time:** {self._format_duration(duration)}

"""
    
    def _build_successful_upgrades_section(self, successful: List[FileUpgradeResult]) -> str:
        """Build successful upgrades section"""
        if not successful:
            return ""
        
        report = """## ✅ Successfully Upgraded Files

"""
        
        # Group by number of attempts
        by_attempts = {}
        for result in successful:
            by_attempts.setdefault(result.attempts, []).append(result)
        
        # Show files that needed multiple attempts first (most interesting)
        for attempts in sorted(by_attempts.keys(), reverse=True):
            results = by_attempts[attempts]
            if attempts > 1:
                report += f"### Files requiring {attempts} attempts ({len(results)} files)\n\n"
            
            for result in results[:10]:  # Limit to 10 files per category
                rel_path = os.path.relpath(result.file_path)
                report += f"#### `{rel_path}`\n\n"
                
                if result.api_changes:
                    report += "**API Changes:**\n"
                    for change in result.api_changes:
                        report += f"- {change}\n"
                    report += "\n"
                
                if result.diff and attempts > 1:
                    # Show diff for files that needed multiple attempts
                    report += "<details>\n<summary>View Changes</summary>\n\n```diff\n"
                    diff_lines = result.diff.split('\n')[:30]
                    report += '\n'.join(diff_lines)
                    if len(result.diff.split('\n')) > 30:
                        report += f"\n... ({len(result.diff.split('\n')) - 30} more lines)"
                    report += "\n```\n</details>\n\n"
            
            if len(results) > 10:
                report += f"*... and {len(results) - 10} more files*\n\n"
        
        return report
    
    def _build_failed_upgrades_section(self, failed: List[FileUpgradeResult]) -> str:
        """Build failed upgrades section"""
        if not failed:
            return ""
        
        report = """## ❌ Failed Upgrades

The following files could not be automatically upgraded:

"""
        
        # Group by error type
        by_error = {}
        for result in failed:
            error_type = result.error.split(':')[0] if result.error else "Unknown"
            by_error.setdefault(error_type, []).append(result)
        
        for error_type, results in sorted(by_error.items(), key=lambda x: len(x[1]), reverse=True):
            report += f"### {error_type} ({len(results)} files)\n\n"
            
            for result in results[:5]:  # Show first 5 of each type
                rel_path = os.path.relpath(result.file_path)
                report += f"- **`{rel_path}`**\n"
                if result.error:
                    report += f"  - Error: {result.error}\n"
                report += f"  - Attempts: {result.attempts}\n"
            
            if len(results) > 5:
                report += f"\n*... and {len(results) - 5} more files*\n"
            
            report += "\n"
        
        return report
    
    def _build_statistics_section(self, stats: Dict) -> str:
        """Build detailed statistics section"""
        report = """## 📊 Detailed Statistics

"""
        
        # API change frequency
        if stats['change_counts']:
            report += "### Most Common API Migrations\n\n"
            sorted_changes = sorted(stats['change_counts'].items(), key=lambda x: x[1], reverse=True)
            
            for change, count in sorted_changes[:10]:
                pct = count / stats['successful'] * 100 if stats['successful'] > 0 else 0
                report += f"- **{change}**: {count} files ({pct:.1f}%)\n"
            
            report += "\n"
        
        # Attempt distribution
        report += "### Upgrade Attempt Distribution\n\n"
        attempt_dist = {}
        for result in self.results:
            attempt_dist[result.attempts] = attempt_dist.get(result.attempts, 0) + 1
        
        for attempts in sorted(attempt_dist.keys()):
            count = attempt_dist[attempts]
            pct = count / stats['total'] * 100 if stats['total'] > 0 else 0
            report += f"- **{attempts} attempt(s)**: {count} files ({pct:.1f}%)\n"
        
        report += "\n"
        return report
    
    def _build_recommendations_section(
        self,
        successful: List[FileUpgradeResult],
        failed: List[FileUpgradeResult]
    ) -> str:
        """Build recommendations section"""
        report = """## 💡 Recommendations

"""
        
        if successful:
            report += f"""### ✅ Immediate Actions
1. **Test Upgraded Files**: Run your test suite on the {len(successful)} successfully upgraded files
2. **Review Critical Changes**: Pay special attention to files that required multiple attempts
3. **Update Dependencies**: Install the updated dependencies from requirements.txt
4. **Gradual Rollout**: Consider deploying upgraded modules incrementally

"""
        
        if failed:
            report += f"""### ⚠️ Manual Review Required
{len(failed)} files require manual attention:
1. Review error messages for each failed file
2. Consider upgrading dependencies first, then retry
3. Some files may have complex patterns that need human judgment
4. Use the diff from successful files as a reference

"""
        
        report += """### 🔄 Next Steps
1. **Version Control**: Commit successful upgrades before manual fixes
2. **Documentation**: Update your documentation to reflect API changes
3. **Testing**: Comprehensive testing is essential after migration
4. **Monitoring**: Monitor for runtime issues after deployment

"""
        
        return report


def generate_upgrade_report(
    results: List[FileUpgradeResult],
    dependency_changes: List[str],
    output_path: str,
    cost_usd: float = 0.0,
    total_tokens: int = 0
) -> None:
    """
    Convenience function to generate upgrade report
    
    Args:
        results: List of file upgrade results
        dependency_changes: List of dependency update changes
        output_path: Path to save report
        cost_usd: Total cost in USD
        total_tokens: Total tokens used
    """
    generator = ReportGenerator()
    
    for result in results:
        generator.add_file_result(result)
    
    generator.add_dependency_changes(dependency_changes)
    generator.set_cost_info(cost_usd, total_tokens)
    generator.generate_report(output_path)