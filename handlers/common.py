from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from aiogram.utils.keyboard import InlineKeyboardBuilder
import config
from models import registry
import uuid

router = Router()

def get_detailed_rules() -> str:
    return (
        "📖 <b>قواعد وتعليمات لعبة Mythikra:</b>\n\n"
        "Mythikra هي لعبة تفاعلية يتنافس فيها لاعبان لتخمين الكلمة السرية للخصم. "
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
        "✨ <b>مرحباً بك في بوت لعبة Mythikra!</b> ✨\n\n"
        "لعبة تخمين الأفكار والكلمات التفاعلية مباشرة داخل قنوات ومجموعات تيليجرام. "
        "يتنافس لاعبان على تخمين كلمات بعضهما البعض، والجمهور يتابع الحماس!\n\n"
        "🎮 <b>كيف تلعب؟</b>\n"
        "1️⃣ ينضم لاعبان للمباراة من خلال الضغط على زر الانضمام.\n"
        "2️⃣ يرسل البوت رسالة خاصة لكل لاعب لاختيار كلمته السرية.\n"
        "3️⃣ يتبادل اللاعبان الأدوار بطرح الأسئلة أو التخمينات في الخاص.\n\n"
        "👑 <b>أوامر إدارة اللعبة (لمشرفي القنوات والمجموعات):</b>\n"
        "• لبدء مباراة جديدة: /newmatch\n"
        "• لإلغاء مباراة نشطة: /cancelmatch\n"
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
        "ℹ️ <b>تعليمات بوت لعبة Mythikra:</b>\n\n"
        "• اللعبة تُلعب بشكل كامل في الخاص مع البوت (لإدخال الأسئلة والإجابات والكلمات السرية)، بينما يتم عرض النتيجة والتقدم في القناة أو المجموعة.\n"
        "• يرجى بدء المحادثة مع البوت في الخاص أولاً قبل الضغط على زر الانضمام لتجنب مشاكل التواصل.\n\n"
        "👑 <b>أوامر الإدارة:</b>\n"
        "• /newmatch - إنشاء مباراة جديدة (في الخاص للمشرفين، أو مباشرة في المجموعات)\n"
        "• /cancelmatch - إلغاء مباراة جارية حالياً\n"
    )
    await message.reply(text, parse_mode="HTML")

# Inline query to start game challenge anywhere
@router.inline_query()
async def handle_inline_query(inline_query: types.InlineQuery):
    match_id = uuid.uuid4().hex[:8]
    category = inline_query.query.strip() if inline_query.query.strip() else "عام"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🎮 انضمام للمباراة", callback_data=f"join_match:{match_id}")
    
    text = (
        f"🎮 <b>تحدي لعبة Mythikra جديد!</b>\n"
        f"🏷️ <b>التصنيف:</b> {category}\n\n"
        f"⏳ بانتظار انضمام لاعبين اثنين لبدء التحدي..."
    )
    
    # Register game with placeholder channel ID (0)
    match = registry.create_match(0, "مباراة سريعة", category, inline_query.from_user.id)
    match.is_group_match = True
    
    result = InlineQueryResultArticle(
        id=match_id,
        title="🎮 بدء تحدي Mythikra",
        description=f"ابدأ مباراة تحدي جديدة في تصنيف: {category}",
        input_message_content=InputTextMessageContent(
            message_text=text,
            parse_mode="HTML"
        ),
        reply_markup=builder.as_markup()
    )
    
    await inline_query.answer([result], is_personal=True, cache_time=0)
