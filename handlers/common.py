from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from aiogram.utils.keyboard import InlineKeyboardBuilder
import config
import uuid

router = Router()

def get_detailed_rules() -> str:
    return (
        "📖 <b>قواعد وتعليمات لعبة التخمين:</b>\n\n"
        "لعبة التخمين هي لعبة تفاعلية يتنافس فيها لاعبان لتخمين الكلمة السرية للخصم. "
        "البوت يدير المباراة وينظم الأدوار بالكامل في الخاص، ويعرض تقدم المباراة للجمهور في القناة أو المجموعة.\n\n"
        "🎮 <b>سير اللعبة التفصيلي:</b>\n"
        "1️⃣ <b>بدء اللعبة:</b> ينضم لاعبان للمباراة بالضغط على زر (انضمام).\n"
        "2️⃣ <b>الكلمات السرية:</b> يطلب البوت من كل لاعب اختيار كلمة سرية سرًا من التصنيف المحدد.\n"
        "3️⃣ <b>تبادل الأدوار:</b> عندما يحين دورك، يظهر لك في الخاص 3 خيارات:\n"
        "   • ❓ <b>طرح سؤال:</b> تكتب سؤالاً يجاوب عليه خصمك بـ (نعم) أو (لا) أو يعترض عليه بـ (سؤال محروق).\n"
        "   • 🎯 <b>إعلان تخمين:</b> تكتب تخمينك للكلمة السرية لخصمك ويؤكده بـ (صحيح) أو (خطأ).\n"
        "   • 🚪 <b>انسحاب:</b> تعلن انسحابك وتنتهي المباراة بخسارتك.\n\n"
        "🔥 <b>السؤال المحروق:</b> إذا سألك الخصم سؤالاً سألته أنت سابقاً أو سؤالاً مكرراً، يمكنك الضغط على <b>(سؤال محروق)</b> لرفضه. سيُطلب من الخصم طرح سؤال آخر غير محروق ولن يفقد دوره.\n\n"
        "⏳ <b>الحدود والتعادل:</b> للمدير خيار تحديد حد أقصى للأسئلة والتخمينات. إذا نفدت خيارات كلا اللاعبين، تنتهي المباراة بالتعادل تلقائياً."
    )

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="📖 تعليمات اللعبة", callback_data="show_rules")
    builder.button(text="🎮 ابدأ التحدي الآن", switch_inline_query_current_chat="")
    builder.adjust(1)
    
    text = (
        "✨ <b>مرحباً بك في بوت لعبة التخمين!</b> ✨\n\n"
        "لعبة تخمين الأفكار والكلمات التفاعلية مباشرة داخل قنوات ومجموعات تيليجرام والمحادثات الخاصة. "
        "يتنافس لاعبان على تخمين كلمات بعضهما البعض، والجمهور يتابع الحماس!\n\n"
        "🎮 <b>كيف تلعب؟</b>\n"
        "1️⃣ ينضم لاعبان للمباراة من خلال الضغط على زر الانضمام.\n"
        "2️⃣ يرسل البوت رسالة خاصة لكل لاعب لاختيار كلمته السرية.\n"
        "3️⃣ يتبادل اللاعبان الأدوار بطرح الأسئلة أو التخمينات في الخاص.\n\n"
        "👑 <b>أوامر إدارة اللعبة (لمشرفي القنوات والمجموعات):</b>\n"
        "• لبدء مباراة جديدة: /newmatch\n"
        "• لإلغاء مباراة نشطة: /cancelmatch\n\n"
        "📢 <i>ملاحظة: يشترط استخدام البوت الاشتراك في القناة الرئيسية: {config.REQUIRED_CHANNEL}</i>"
    )
    await message.reply(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.message(Command("rules"))
async def cmd_rules(message: types.Message):
    await message.reply(get_detailed_rules(), parse_mode="HTML")

@router.callback_query(F.data == "show_rules")
async def process_show_rules(callback: types.CallbackQuery):
    await callback.message.reply(get_detailed_rules(), parse_mode="HTML")
    await callback.answer()

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "ℹ️ <b>تعليمات بوت لعبة التخمين:</b>\n\n"
        "• اللعبة تُلعب بشكل كامل في الخاص مع البوت (لإدخال الأسئلة والإجابات والكلمات السرية)، بينما يتم عرض النتيجة والتقدم في القناة أو المجموعة.\n"
        "• يرجى بدء المحادثة مع البوت في الخاص أولاً قبل الضغط على زر الانضمام لتجنب مشاكل التواصل.\n\n"
        "👑 <b>أوامر الإدارة:</b>\n"
        "• /newmatch - إنشاء مباراة جديدة (في الخاص للمشرفين، أو مباشرة في المجموعات)\n"
        "• /cancelmatch - إلغاء مباراة جارية حالياً\n"
    )
    await message.reply(text, parse_mode="HTML")

# Stateless Inline Query Handler
@router.inline_query()
async def handle_inline_query(inline_query: types.InlineQuery):
    user_query = inline_query.query.strip()
    category = user_query if user_query else "عام"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🎮 انضمام للمباراة", callback_data=f"join_inline:{category}")
    
    text = (
        f"🎮 <b>تحدي مباراة تخمين جديدة!</b>\n"
        f"🏷️ <b>التصنيف:</b> {category}\n\n"
        f"⏳ بانتظار انضمام اللاعبين (0/2)..."
    )
    
    description_text = (
        f"التصنيف الحالي: ({category}) - اضغط لنشر التحدي"
        if user_query
        else "💡 اكتب اسم التصنيف بعد اسم البوت (مثال: @bot أفلام)"
    )
    
    results = [
        InlineQueryResultArticle(
            id=f"inline_{uuid.uuid4().hex[:6]}",
            title=f"🎮 بدء مباراة تخمين (التصنيف: {category})",
            description=description_text,
            input_message_content=InputTextMessageContent(
                message_text=text,
                parse_mode="HTML"
            ),
            reply_markup=builder.as_markup()
        )
    ]
    
    await inline_query.answer(results, is_personal=True, cache_time=0)
