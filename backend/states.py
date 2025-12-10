"""
Состояния FSM для бота
"""
from aiogram.fsm.state import State, StatesGroup


class GenericFSM(StatesGroup):
    """
    Основной FSM для сценария онбординга.
    """
    InProgress = State()


class WaitlistFSM(StatesGroup):
    """
    FSM для добавления пользователя в лист ожидания.
    """
    waiting_for_contact = State()


class BookingStates(StatesGroup):
    """
    FSM для процесса бронирования урока.
    """
    selecting_slot = State()  # Выбор слота для бронирования
    confirming = State()  # Подтверждение бронирования
    selecting_event_to_reschedule = State()  # Выбор записи для переноса
    rescheduling = State()  # Выбор нового времени для переноса
    selecting_event_to_cancel = State()  # Выбор записи для отмены
    choosing_child = State()
    choosing_date = State()
    choosing_time = State()
    rescheduling_in_progress = State()


class OnboardingFSM(StatesGroup):
    """
    Состояния для пошагового сценария онбординга.
    """
    # Шаги анкеты
    entering_parent_name = State()
    entering_child_name = State()
    entering_child_age = State()
    entering_interests = State()
    
    # Новые шаги для "умного" сбора контактов
    choose_contact_method = State()
    entering_phone = State()
    entering_email = State()
    
    # Финальный шаг подтверждения
    confirm_data = State()


class CancellationStates(StatesGroup):
    """
    Состояния для процесса отмены записи со сбором обратной связи.
    """
    awaiting_reason = State()  # Состояние ожидания текстовой причины отмены


class RescheduleStates(StatesGroup):
    """
    Состояния для многошагового сценария переноса пробного урока.
    """
    choosing_lesson = State()  # Шаг 1: Пользователь выбирает, какой из уроков перенести
    choosing_new_date = State()  # Шаг 2: Пользователь выбирает новую дату
    choosing_new_time = State()  # Шаг 3: Пользователь выбирает новое время
    confirming = State()


class FeedbackStates(StatesGroup):
    """Состояния для сбора обратной связи"""
    choosing_child = State() 
    waiting_for_feedback = State()
    checking_feedback = State()
    feedback_complete = State()


