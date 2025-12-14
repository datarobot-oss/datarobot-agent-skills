#!/usr/bin/env python3
"""
List trained models for a project.

Usage:
    python list_models.py <project_id> [sort_by]

Sort options: AUC, RMSE, accuracy (default: by validation score)
"""

import sys
import json
import os
import datarobot as dr

def list_models(project_id: str, sort_by: str = "validation") -> dict:
    """
    List trained models for a project.
    
    Args:
        project_id: The project ID
        sort_by: Sort option - "validation", "AUC", "RMSE", etc.
        
    Returns:
        List of models with metrics
    """
    # Initialize client
    client = dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com")
    )
    
    models = dr.Model.list(project_id)
    
    # Get model details with metrics
    model_list = []
    for model in models:
        try:
            metrics = model.get_metrics()
            model_info = {
                "model_id": model.id,
                "model_type": model.model_type,
                "blueprint_id": model.blueprint_id,
                "metrics": metrics
            }
            model_list.append(model_info)
        except:
            model_info = {
                "model_id": model.id,
                "model_type": model.model_type,
                "blueprint_id": model.blueprint_id
            }
            model_list.append(model_info)
    
    # Sort models
    if sort_by == "AUC" and model_list:
        model_list.sort(key=lambda x: x.get("metrics", {}).get("AUC", 0), reverse=True)
    elif sort_by == "RMSE" and model_list:
        model_list.sort(key=lambda x: x.get("metrics", {}).get("RMSE", float('inf')))
    
    return {
        "project_id": project_id,
        "model_count": len(model_list),
        "models": model_list
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python list_models.py <project_id> [sort_by]", file=sys.stderr)
        sys.exit(1)
    
    project_id = sys.argv[1]
    sort_by = sys.argv[2] if len(sys.argv) > 2 else "validation"
    
    try:
        result = list_models(project_id, sort_by)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

