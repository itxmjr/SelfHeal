from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from selfheal.engine.scorer import calculate_score

@patch("selfheal.engine.scorer.get_connection")
@patch("selfheal.engine.scorer.load_config")
def test_calculate_score_no_tasks(mock_load_config, mock_get_conn):
    """Test scoring when there are no tasks."""
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn
    mock_load_config.return_value = {
        "scoring": {
            "weights": {"task_completion": 40, "time_utilization": 30, "goal_alignment": 20, "consistency_bonus": 10},
            "streak_threshold": 70
        }
    }
    
    # Mock empty tasks
    with patch("selfheal.engine.scorer.get_todays_tasks", return_value=[]):
        result = calculate_score()
        
        assert result["score"] == 0.0

@patch("selfheal.engine.scorer.get_connection")
@patch("selfheal.engine.scorer.load_config")
def test_calculate_score_all_done(mock_load_config, mock_get_conn):
    """Test scoring when all tasks are completed."""
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn
    mock_load_config.return_value = {
        "scoring": {
            "weights": {"task_completion": 40, "time_utilization": 30, "goal_alignment": 20, "consistency_bonus": 10},
            "streak_threshold": 70
        }
    }
    
    mock_tasks = [
        {"id": 1, "status": "done", "priority": "high", "scheduled_start": "09:00", "scheduled_end": "10:00", "actual_start": "09:00", "actual_end": "10:00", "goal_id": 1},
        {"id": 2, "status": "done", "priority": "medium", "scheduled_start": "11:00", "scheduled_end": "12:00", "actual_start": "11:00", "actual_end": "12:00", "goal_id": 2},
    ]
    
    with patch("selfheal.engine.scorer.get_todays_tasks", return_value=mock_tasks):
        with patch("selfheal.engine.scorer.get_streak", return_value=5):
            with patch("selfheal.engine.scorer.save_score"):
                result = calculate_score()
                
                assert result["total"] == 2
                assert result["done"] == 2
                assert result["task_completion"] == 40.0  # Max score
                assert result["time_utilization"] == 30.0  # Max score (started on time)
                assert result["goal_alignment"] == 20.0    # Max score (all have goal_id)
                assert result["score"] == 100.0             # Everything perfect + consistency bonus
