from django import forms
from decimal import Decimal
from .models import AttendanceSettings


class AttendanceSettingsAdminForm(forms.ModelForm):
    rank_1 = forms.DecimalField(label='Rank 1 amount', required=False, min_value=0)
    rank_2 = forms.DecimalField(label='Rank 2 amount', required=False, min_value=0)
    rank_3 = forms.DecimalField(label='Rank 3 amount', required=False, min_value=0)
    rank_4 = forms.DecimalField(label='Rank 4 amount', required=False, min_value=0)
    rank_5 = forms.DecimalField(label='Rank 5 amount', required=False, min_value=0)
    rank_6 = forms.DecimalField(label='Rank 6 amount', required=False, min_value=0)

    # Daily sequence fields
    day_1 = forms.DecimalField(label='Day 1 Reward', required=False, min_value=0)
    day_2 = forms.DecimalField(label='Day 2 Reward', required=False, min_value=0)
    day_3 = forms.DecimalField(label='Day 3 Reward', required=False, min_value=0)
    day_4 = forms.DecimalField(label='Day 4 Reward', required=False, min_value=0)
    day_5 = forms.DecimalField(label='Day 5 Reward', required=False, min_value=0)
    day_6 = forms.DecimalField(label='Day 6 Reward', required=False, min_value=0)
    day_7 = forms.DecimalField(label='Day 7 Reward', required=False, min_value=0)
    day_8 = forms.DecimalField(label='Day 8 Reward', required=False, min_value=0)
    day_9 = forms.DecimalField(label='Day 9 Reward', required=False, min_value=0)
    day_10 = forms.DecimalField(label='Day 10 Reward', required=False, min_value=0)
    day_11 = forms.DecimalField(label='Day 11 Reward', required=False, min_value=0)
    day_12 = forms.DecimalField(label='Day 12 Reward', required=False, min_value=0)
    day_13 = forms.DecimalField(label='Day 13 Reward', required=False, min_value=0)
    day_14 = forms.DecimalField(label='Day 14 Reward', required=False, min_value=0)
    day_15 = forms.DecimalField(label='Day 15 Reward', required=False, min_value=0)
    day_16 = forms.DecimalField(label='Day 16 Reward', required=False, min_value=0)
    day_17 = forms.DecimalField(label='Day 17 Reward', required=False, min_value=0)
    day_18 = forms.DecimalField(label='Day 18 Reward', required=False, min_value=0)
    day_19 = forms.DecimalField(label='Day 19 Reward', required=False, min_value=0)
    day_20 = forms.DecimalField(label='Day 20 Reward', required=False, min_value=0)
    day_21 = forms.DecimalField(label='Day 21 Reward', required=False, min_value=0)
    day_22 = forms.DecimalField(label='Day 22 Reward', required=False, min_value=0)
    day_23 = forms.DecimalField(label='Day 23 Reward', required=False, min_value=0)
    day_24 = forms.DecimalField(label='Day 24 Reward', required=False, min_value=0)
    day_25 = forms.DecimalField(label='Day 25 Reward', required=False, min_value=0)
    day_26 = forms.DecimalField(label='Day 26 Reward', required=False, min_value=0)
    day_27 = forms.DecimalField(label='Day 27 Reward', required=False, min_value=0)
    day_28 = forms.DecimalField(label='Day 28 Reward', required=False, min_value=0)
    day_29 = forms.DecimalField(label='Day 29 Reward', required=False, min_value=0)
    day_30 = forms.DecimalField(label='Day 30 Reward', required=False, min_value=0)
    day_31 = forms.DecimalField(label='Day 31 Reward', required=False, min_value=0)

    class Meta:
        model = AttendanceSettings
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cycle_days_raw = None
        if self.data:
            cycle_days_raw = (self.data.get('daily_cycle_days') or '').strip()
        cycle_days = None
        if cycle_days_raw:
            try:
                cycle_days = int(cycle_days_raw)
            except Exception:
                cycle_days = None
        if cycle_days is None:
            cycle_days = int(getattr(self.instance, 'daily_cycle_days', 7) or 7)
        if cycle_days <= 0:
            cycle_days = 7
        if cycle_days > 31:
            cycle_days = 31

        rr = self.instance.rank_rewards or {}
        for i in range(1, 7):
            key = str(i)
            if key in rr:
                try:
                    self.fields[f'rank_{i}'].initial = Decimal(str(rr[key]))
                except Exception:
                    self.fields[f'rank_{i}'].initial = rr[key]
        
        dr = self.instance.daily_rewards or {}
        for i in range(1, cycle_days + 1):
            key = str(i)
            if key in dr and f'day_{i}' in self.fields:
                try:
                    self.fields[f'day_{i}'].initial = Decimal(str(dr[key]))
                except Exception:
                    self.fields[f'day_{i}'].initial = dr[key]

        reward_type = None
        if self.data:
            reward_type = (self.data.get('reward_type') or '').strip() or None
        if reward_type is None:
            reward_type = getattr(self.instance, 'reward_type', None)
        if reward_type == 'daily' and 'bonus_7_days' in self.fields:
            self.fields['bonus_7_days'].label = f'Bonus {cycle_days} days'

    def save(self, commit=True):
        instance = super().save(commit=False)
        rr = {}
        for i in range(1, 7):
            val = self.cleaned_data.get(f'rank_{i}')
            if val is not None:
                # Store as float to keep JSON simple
                rr[str(i)] = float(val)
        instance.rank_rewards = rr
        
        dr = {}
        cycle_days = int(getattr(instance, 'daily_cycle_days', 7) or 7)
        if cycle_days <= 0:
            cycle_days = 7
        if cycle_days > 31:
            cycle_days = 31
        for i in range(1, cycle_days + 1):
            val = self.cleaned_data.get(f'day_{i}')
            if val is not None:
                dr[str(i)] = float(val)
        instance.daily_rewards = dr
        
        if commit:
            instance.save()
        return instance
