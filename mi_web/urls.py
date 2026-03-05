"""
URL configuration for mi_web project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views  
from genaigrader.views.auth_views import signup  
from genaigrader.views.course_views import course_view, update_course, delete_course, delete_exam, update_exam, export_all_evaluations, export_course_evaluations
from genaigrader.views.evaluate_views import evaluate_view, upload_file
from genaigrader.views.batch_evaluations_view import batch_evaluations_view
from genaigrader.views.exam_details_view import exam_detail, delete_evaluation, question_analytics
from genaigrader.views.analysis_view import analysis_view
from genaigrader.views.api_views import api_view, update_model, delete_model, create_model, pull_model
from genaigrader.views.home_view import home_view

urlpatterns = [
    path('admin/', admin.site.urls),
    

    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),  
    path('accounts/signup/', signup, name='signup'),
    
 
    path('evaluate/', evaluate_view, name='evaluate'),
    path('course/', course_view, name='course'),

    #This is the URL that the frontend will call to upload the exam file. It is handled by the upload_file view which processes the file and creates the necessary database entries.
    path('upload/', upload_file, name='upload_file'),
    path('exam/<int:exam_id>/', exam_detail, name='exam_detail'),
    #TODO ADD URL FOR THE ENDPOINT OF THE QUESTIONS ANALYTICS
    path('question/<int:question_id>/analytics/', question_analytics, name='question_analytics'),
    path('analysis/', analysis_view, name='analysis'),
    path('api/', api_view, name='api'),
    path('batch-evaluations/', batch_evaluations_view, name='batch_evaluations'),

    path('export/all/', export_all_evaluations, name='export_all_evaluations'),
    path('export/course/<int:course_id>/', export_course_evaluations, name='export_course_evaluations'),
    path('evaluation/delete/<int:eval_id>/', delete_evaluation, name='delete_evaluation'),
    path('course/update/<int:course_id>/', update_course, name='update_course'),
    path('course/delete/<int:course_id>/', delete_course, name='delete_course'),
    path('course/exam/update/<int:exam_id>/', update_exam, name='update_exam'),
    path('course/exam/delete/<int:exam_id>/', delete_exam, name='delete_exam'),
    path('model/update/<int:model_id>/', update_model, name='update_model'),
    path('model/delete/<int:model_id>/', delete_model, name='delete_model'),
    path('model/create/', create_model, name='create_model'),

    path('model/pull/', pull_model, name='pull_model'),
    path('', home_view, name='home'),



]