#!/bin/bash

# rye run python plan_explanations.py --explainer SQAPlanner --search confidence --model XGBoost --verbose --project $1
rye run python flip_exp.py --explainer LIME --model XGBoost --verbose --project "$1"
