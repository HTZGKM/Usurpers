from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    FieldList,
    Form,
    FormField,
    IntegerField,
    StringField,
    SubmitField,
)
from wtforms.validators import InputRequired, Length, NumberRange, Optional, ValidationError


class BookingForm(FlaskForm):
    booking_date = DateField(
        "用餐日期",
        format="%Y-%m-%d",
        validators=[InputRequired("请选择用餐日期。")],
    )
    time_slot_id = IntegerField(
        "用餐时段",
        validators=[InputRequired("请选择用餐时段。"), NumberRange(min=1)],
    )
    party_size = IntegerField(
        "用餐人数",
        validators=[InputRequired("请输入用餐人数。"), NumberRange(min=1)],
    )
    submit = SubmitField("确认订座")


class BookingEditForm(BookingForm):
    submit = SubmitField("保存预订修改")


class CancelBookingForm(FlaskForm):
    submit = SubmitField("取消预订")


class OrderItemForm(Form):
    dish_id = IntegerField(
        "菜品编号",
        validators=[InputRequired("缺少菜品编号。"), NumberRange(min=1)],
    )
    quantity = IntegerField(
        "数量",
        validators=[InputRequired("请输入数量。"), NumberRange(min=1)],
    )
    note = StringField("备注", validators=[Optional(), Length(max=200)])


class OrderForm(FlaskForm):
    items = FieldList(FormField(OrderItemForm))
    submit = SubmitField("确认下单")

    def validate_items(self, items):
        if not items.entries:
            raise ValidationError("请至少选择一道菜。")


class PaymentForm(FlaskForm):
    submit = SubmitField("确认付款")
