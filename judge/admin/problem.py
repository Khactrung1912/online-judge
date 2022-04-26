from operator import attrgetter
import statistics

from django import forms
from django.contrib import admin
from django.db import transaction
from django.db.models import Q, Avg, Count
from django.db.models.aggregates import StdDev
from django.forms import ModelForm
from django.urls import reverse_lazy
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy as _, ungettext
from reversion.admin import VersionAdmin
from reversion_compare.admin import CompareVersionAdmin


from judge.models import LanguageLimit, Problem, ProblemClarification, ProblemTranslation, Profile, Solution
from judge.widgets import AdminHeavySelect2MultipleWidget, AdminSelect2MultipleWidget, AdminSelect2Widget, \
    CheckboxSelectMultipleWithSelectAll, HeavyPreviewAdminPageDownWidget, HeavyPreviewPageDownWidget


class ProblemForm(ModelForm):
    change_message = forms.CharField(max_length=256, label='Edit reason', required=False)

    def __init__(self, *args, **kwargs):
        super(ProblemForm, self).__init__(*args, **kwargs)
        self.fields['authors'].widget.can_add_related = False
        self.fields['curators'].widget.can_add_related = False
        self.fields['testers'].widget.can_add_related = False
        self.fields['banned_users'].widget.can_add_related = False
        self.fields['change_message'].widget.attrs.update({
            'placeholder': gettext('Describe the changes you made (optional)'),
        })

    class Meta:
        widgets = {
            'authors': AdminHeavySelect2MultipleWidget(data_view='profile_select2', attrs={'style': 'width: 100%'}),
            'curators': AdminHeavySelect2MultipleWidget(data_view='profile_select2', attrs={'style': 'width: 100%'}),
            'testers': AdminHeavySelect2MultipleWidget(data_view='profile_select2', attrs={'style': 'width: 100%'}),
            'banned_users': AdminHeavySelect2MultipleWidget(data_view='profile_select2',
                                                            attrs={'style': 'width: 100%'}),
            'organizations': AdminHeavySelect2MultipleWidget(data_view='organization_select2',
                                                             attrs={'style': 'width: 100%'}),
            'types': AdminSelect2MultipleWidget,
            'group': AdminSelect2Widget,
        }
        if HeavyPreviewAdminPageDownWidget is not None:
            widgets['description'] = HeavyPreviewAdminPageDownWidget(preview=reverse_lazy('problem_preview'))


class ProblemCreatorListFilter(admin.SimpleListFilter):
    title = parameter_name = 'creator'

    def lookups(self, request, model_admin):
        queryset = Profile.objects.exclude(authored_problems=None).values_list('user__username', flat=True)
        return [(name, name) for name in queryset]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset
        return queryset.filter(authors__user__username=self.value())


class LanguageLimitInlineForm(ModelForm):
    class Meta:
        widgets = {'language': AdminSelect2Widget}


class LanguageLimitInline(admin.TabularInline):
    model = LanguageLimit
    fields = ('language', 'time_limit', 'memory_limit')
    form = LanguageLimitInlineForm


class ProblemClarificationForm(ModelForm):
    class Meta:
        if HeavyPreviewPageDownWidget is not None:
            widgets = {'description': HeavyPreviewPageDownWidget(preview=reverse_lazy('comment_preview'))}


class ProblemClarificationInline(admin.StackedInline):
    model = ProblemClarification
    fields = ('description',)
    form = ProblemClarificationForm
    extra = 0


class ProblemSolutionForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(ProblemSolutionForm, self).__init__(*args, **kwargs)
        self.fields['authors'].widget.can_add_related = False

    class Meta:
        widgets = {
            'authors': AdminHeavySelect2MultipleWidget(data_view='profile_select2', attrs={'style': 'width: 100%'}),
        }

        if HeavyPreviewAdminPageDownWidget is not None:
            widgets['content'] = HeavyPreviewAdminPageDownWidget(preview=reverse_lazy('solution_preview'))


class ProblemSolutionInline(admin.StackedInline):
    model = Solution
    fields = ('is_public', 'publish_on', 'authors', 'content')
    form = ProblemSolutionForm
    extra = 0


class ProblemTranslationForm(ModelForm):
    class Meta:
        if HeavyPreviewAdminPageDownWidget is not None:
            widgets = {'description': HeavyPreviewAdminPageDownWidget(preview=reverse_lazy('problem_preview'))}


class ProblemTranslationInline(admin.StackedInline):
    model = ProblemTranslation
    fields = ('language', 'name', 'description')
    form = ProblemTranslationForm
    extra = 0


class ProblemAdmin(CompareVersionAdmin):
    fieldsets = (
        (None, {
            'fields': (
                'code', 'name', 'is_public', 'is_manually_managed', 'date', 'authors', 'curators', 'testers',
                'is_organization_private', 'organizations', 'description', 'license',
            ),
        }),
        (_('Social Media'), {'classes': ('collapse',), 'fields': ('og_image', 'summary')}),
        (_('Taxonomy'), {'fields': ('types', 'group')}),
        (_('Points'), {'fields': (('points', 'partial'), 'short_circuit')}),
        (_('Limits'), {'fields': ('time_limit', 'memory_limit')}),
        (_('Language'), {'fields': ('allowed_languages',)}),
        (_('Justice'), {'fields': ('banned_users',)}),
        (_('History'), {'fields': ('change_message',)}),
    )
    list_display = ['code', 'name', 'show_authors', 'points', 'vote_cnt', 'vote_mean', 'vote_median', 'vote_std', 'is_public', 'show_public']
    ordering = ['code']
    search_fields = ('code', 'name', 'authors__user__username', 'curators__user__username')
    inlines = [LanguageLimitInline, ProblemClarificationInline, ProblemSolutionInline, ProblemTranslationInline]
    list_max_show_all = 1000
    actions_on_top = True
    actions_on_bottom = True
    list_filter = ('is_public', ProblemCreatorListFilter)
    form = ProblemForm
    date_hierarchy = 'date'

    def get_actions(self, request):
        actions = super(ProblemAdmin, self).get_actions(request)

        if request.user.has_perm('judge.change_public_visibility'):
            func, name, desc = self.get_action('make_public')
            actions[name] = (func, name, desc)

            func, name, desc = self.get_action('make_private')
            actions[name] = (func, name, desc)

        return actions

    def get_readonly_fields(self, request, obj=None):
        fields = self.readonly_fields
        if not request.user.has_perm('judge.change_public_visibility'):
            fields += ('is_public',)
        if not request.user.has_perm('judge.change_manually_managed'):
            fields += ('is_manually_managed',)
        return fields

    def show_authors(self, obj):
        return ', '.join(map(attrgetter('user.username'), obj.authors.all()))

    show_authors.short_description = _('Authors')

    def show_public(self, obj):
        return format_html('<a href="{1}">{0}</a>', gettext('View on site'), obj.get_absolute_url())

    show_public.short_description = ''

    def _rescore(self, request, problem_id):
        from judge.tasks import rescore_problem
        transaction.on_commit(rescore_problem.s(problem_id).delay)

    def make_public(self, request, queryset):
        count = queryset.update(is_public=True)
        for problem_id in queryset.values_list('id', flat=True):
            self._rescore(request, problem_id)
        self.message_user(request, ungettext('%d problem successfully marked as public.',
                                             '%d problems successfully marked as public.',
                                             count) % count)

    make_public.short_description = _('Mark problems as public')

    def make_private(self, request, queryset):
        count = queryset.update(is_public=False)
        for problem_id in queryset.values_list('id', flat=True):
            self._rescore(request, problem_id)
        self.message_user(request, ungettext('%d problem successfully marked as private.',
                                             '%d problems successfully marked as private.',
                                             count) % count)

    make_private.short_description = _('Mark problems as private')

    def get_queryset(self, request):
        queryset = Problem.objects.prefetch_related('authors__user')
        queryset = queryset.annotate(
            _vote_mean=Avg('problem_points_votes__points'),
            _vote_std=StdDev('problem_points_votes__points'),
            _vote_cnt=Count('problem_points_votes__points')
        )
        if request.user.has_perm('judge.edit_all_problem'):
            return queryset

        access = Q()
        if request.user.has_perm('judge.edit_public_problem'):
            access |= Q(is_public=True)
        if request.user.has_perm('judge.edit_own_problem'):
            access |= Q(authors__id=request.profile.id) | Q(curators__id=request.profile.id)
        return queryset.filter(access).distinct() if access else queryset.none()

    def has_change_permission(self, request, obj=None):
        if request.user.has_perm('judge.edit_all_problem') or obj is None:
            return True
        if request.user.has_perm('judge.edit_public_problem') and obj.is_public:
            return True
        if not request.user.has_perm('judge.edit_own_problem'):
            return False
        return obj.is_editor(request.profile)

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name == 'allowed_languages':
            kwargs['widget'] = CheckboxSelectMultipleWithSelectAll()
        return super(ProblemAdmin, self).formfield_for_manytomany(db_field, request, **kwargs)

    def get_form(self, *args, **kwargs):
        form = super(ProblemAdmin, self).get_form(*args, **kwargs)
        form.base_fields['authors'].queryset = Profile.objects.all()
        return form

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if form.changed_data and any(f in form.changed_data for f in ('is_public', 'points', 'partial')):
            self._rescore(request, obj.id)

    def construct_change_message(self, request, form, *args, **kwargs):
        if form.cleaned_data.get('change_message'):
            return form.cleaned_data['change_message']
        return super(ProblemAdmin, self).construct_change_message(request, form, *args, **kwargs)

    def vote_mean(self, obj):
        return round(obj._vote_mean, 1) if obj._vote_mean is not None else None
    vote_mean.admin_order_field = '_vote_mean'

    def vote_std(self, obj):
        return round(obj._vote_std, 1) if obj._vote_std is not None else None
    vote_std.admin_order_field = '_vote_std'

    def vote_cnt(self, obj):
        return obj._vote_cnt
    vote_cnt.admin_order_field = '_vote_cnt'

    def vote_median(self, obj):
        votes = obj.problem_points_votes.values_list('points', flat=True)
        return statistics.median(votes) if votes else None        


class ProblemPointsVoteAdmin(admin.ModelAdmin):
    list_display = ('vote_points', 'voter', 'voter_rating', 'voter_point', 'problem_name', 'problem_code', 'problem_points')
    search_fields = ('voter__user__username', 'problem__code', 'problem__name')
    readonly_fields = ('voter', 'problem', 'problem_code', 'problem_points', 'voter_rating', 'voter_point')

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return request.user.has_perm('judge.edit_own_problem')
        return obj.problem.is_editable_by(request.user)

    def lookup_allowed(self, key, value):
        return True

    def problem_code(self, obj):
        return obj.problem.code
    problem_code.short_description = _('Problem code')
    problem_code.admin_order_field = 'problem__code'

    def problem_points(self, obj):
        return obj.problem.points
    problem_points.short_description = _('Points')
    problem_points.admin_order_field = 'problem__points'

    def problem_name(self, obj):
        return obj.problem.name
    problem_name.short_description = _('Problem name')
    problem_name.admin_order_field = 'problem__name'

    def voter_rating(self, obj):
        return obj.voter.rating
    voter_rating.short_description = _('Voter rating')
    voter_rating.admin_order_field = 'voter__rating'

    def voter_point(self, obj):
        return round(obj.voter.performance_points)
    voter_point.short_description = _('Voter point')
    voter_point.admin_order_field = 'voter__performance_points'

    def vote_points(self, obj):
        return obj.points
    vote_points.short_description = _('Vote')